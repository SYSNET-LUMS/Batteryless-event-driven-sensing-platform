from flask import Blueprint, request, jsonify, current_app
from typing import Any, cast
from services.agent_manager import get_agent
import traceback
from config.settings import Config
import math

bp = Blueprint('simulation', __name__, url_prefix='/api')

def update_truck_simulation_state(truck: dict, time_delta_seconds: float, repo, agent=None) -> dict:
    """
    Update truck position and route progress based on simulation time and truck speed
    
    This is the missing piece - trucks actually moving through simulation world!
    """
    try:
        truck_speed_kmh = truck.get('speed', 40.0)  # km/h
        hours_passed = time_delta_seconds / 3600.0  # Convert seconds to hours
        distance_traveled_km = truck_speed_kmh * hours_passed  # Distance truck can travel in this time step
        
        # Get truck's current route/schedule
        route_data = truck.get('current_route', {})
        route_bins = route_data.get('bins', [])
        
        if not route_bins:
            return truck  # No route to follow
        
        # Track route progress
        current_step = truck.get('route_step', 0)
        distance_to_next = truck.get('distance_to_next', 0.0)  # km remaining to next bin
        
        remaining_distance = distance_traveled_km
        
        while remaining_distance > 0 and current_step < len(route_bins):
            if distance_to_next <= remaining_distance:
                # Truck reaches the next bin
                remaining_distance -= distance_to_next
                current_step += 1
                
                if current_step < len(route_bins):
                    # Calculate distance to next bin after this one
                    current_bin = route_bins[current_step - 1]
                    next_bin = route_bins[current_step]
                    distance_to_next = calculate_distance_km(
                        current_bin.get('lat', 0), current_bin.get('lng', 0),
                        next_bin.get('lat', 0), next_bin.get('lng', 0)
                    )
                    
                    # Simulate bin collection (add collection time)
                    collection_time_hours = 5 / 60.0  # 5 minutes
                    if hours_passed >= collection_time_hours:
                        # Truck has time to collect this bin
                        truck['current_load'] = truck.get('current_load', 0) + current_bin.get('current_fill', 0)
                        print(f"🚛 Truck {truck['id']} collected bin {current_bin['id']}")
                    else:
                        # Not enough time in this step, truck is collecting
                        truck['status'] = 'collecting'
                        break
                else:
                    # Reached end of route - return to depot
                    truck['status'] = 'returning'
                    depot = repo.get_depots()[0] if repo.get_depots() else None
                    if depot and current_step > 0:
                        last_bin = route_bins[current_step - 1]
                        distance_to_next = calculate_distance_km(
                            last_bin.get('lat', 0), last_bin.get('lng', 0),
                            depot.get('lat', 0), depot.get('lng', 0)
                        )
            else:
                # Truck is still traveling to next bin
                distance_to_next -= remaining_distance
                remaining_distance = 0
                truck['status'] = 'traveling'
        
        # Update truck state
        truck['route_step'] = current_step
        truck['distance_to_next'] = distance_to_next
        
        # If truck completed route and returned to depot
        if truck['status'] == 'returning' and distance_to_next <= 0:
            truck['status'] = 'available'
            truck['current_load'] = 0
            truck['route_step'] = 0
            truck['distance_to_next'] = 0
            truck['current_route'] = {}
            print(f"✅ Truck {truck['id']} completed route and returned to depot")
            
            # Cleanup: Update proactive dispatch tracking to remove stale assignments
            if agent:
                try:
                    agent.update_truck_assignment_status(truck['id'], 'completed_route')
                    print(f"🧹 Cleaned up assignments for truck {truck['id']}")
                except Exception as e:
                    print(f"⚠️ Error cleaning up truck assignment for {truck['id']}: {e}")
        
        return truck
        
    except Exception as e:
        print(f"⚠️ Error updating truck simulation state: {e}")
        return truck

def calculate_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two points in km (Haversine formula)"""
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat/2) * math.sin(dlat/2) + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
         math.sin(dlng/2) * math.sin(dlng/2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

@bp.route('/start_simulation', methods=['POST'])
def start_simulation():
    """Start simulation"""
    try:
        agent = get_agent()
        app = cast(Any, current_app)
        repo = app.system_repository
        
        if not repo.get_bins() or not repo.get_depots():
            return jsonify({
                "status": "error",
                "message": "Need at least one depot and bins to start simulation"
            }), 400
        
        print("Starting simulation...")
        agent.bins_data = repo.get_bins()
        agent.depot_data = repo.get_depots()
        
        # Mark simulation as started
        agent.simulation_started = True
        print(f"✅ Simulation started - agent_id={id(agent)}")
        
        return jsonify({
            "status": "success",
            "message": "Simplified simulation started",
            "routes": {},
            "decisions": {}
        })
        
    except Exception as e:
        print(f"⚠ Simulation start error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/simulation_step', methods=['POST'])
def simulation_step():
    """Simulation step with coordination support"""
    try:
        data = request.json
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid or missing JSON body"}), 400
        time_delta = data.get('time_delta', 1)
        simulation_time = data.get('simulation_time', 7)
        
        agent = get_agent()
        app = cast(Any, current_app)
        repo = app.system_repository
        schedule_service = app.schedule_service
        
        if agent:
            ready_dispatches = agent.process_waiting_trucks(simulation_time)
            if ready_dispatches:
                print(f"Dispatching {len(ready_dispatches)} trucks after waiting period")
        
        # Check for scheduled dispatches that are ready to execute
        schedule_dispatches = []
        if schedule_service:
            try:
                schedules = repo.get_schedules()
                ready_schedules = schedule_service.find_ready_schedules(schedules, simulation_time)
                
                for schedule_data in ready_schedules:
                    trucks = repo.get_trucks()
                    success, message, dispatch_data = schedule_service.execute_schedule(
                        schedule_data, trucks, simulation_time
                    )
                    
                    if success and dispatch_data:
                        schedule_dispatches.append(dispatch_data)
                        # Mark schedule as executing
                        schedule_data['status'] = 'executing'
                        schedule_data['executed_at'] = simulation_time
                        repo.update_schedule(schedule_data)
                        print(f"📅 Executed schedule {schedule_data['id']}: {message}")
                        
                        # For recurring schedules, we'll complete them after a short delay
                        # This simulates the truck starting its collection route
                        if dispatch_data.get('is_recurring', False):
                            # Complete immediately and regenerate for next occurrence
                            success, complete_msg = schedule_service.complete_schedule_execution(
                                schedule_data, simulation_time + 60, repo  # Complete 1 minute after dispatch
                            )
                            if success:
                                print(f"📅 {complete_msg}")
                    else:
                        print(f"📅 Failed to execute schedule {schedule_data['id']}: {message}")
                        
            except Exception as e:
                print(f"⚠️ Error processing schedules: {e}")
        
        # Update bin fill levels
        bins = repo.get_bins()
        bins_that_hit_threshold = []

        # Pre-compute dynamic thresholds for all bins in a neighbor-aware way
        if agent and repo.get_depots():
            try:
                depot = repo.get_depots()[0]
                # This call updates each bin's dynamic_threshold in-place using neighbor context
                agent.simulation_service.calculate_dynamic_thresholds(bins, simulation_time, depot)
            except Exception as e:
                print(f"⌨ Error calculating dynamic thresholds: {e}")
        
        for bin_item in bins:
            try:
                old_fill = bin_item['fillLevel']
                
                # Use already computed dynamic threshold if present; otherwise fallback to static threshold
                old_dynamic_threshold = bin_item.get('dynamic_threshold', bin_item.get('threshold', 80))
                
                # Update fill level
                hours_passed = time_delta / 3600
                increase = bin_item['fillRate'] * hours_passed
                bin_item['fillLevel'] = min(100, bin_item['fillLevel'] + increase)
                
                # Check threshold
                if old_fill < old_dynamic_threshold and bin_item['fillLevel'] >= old_dynamic_threshold:
                    bins_that_hit_threshold.append(bin_item['id'])
                
                # Update in repository
                repo.update_bin(bin_item['id'], bin_item)
                    
            except Exception as e:
                print(f"⌨ Error processing bin {bin_item.get('id', 'unknown')}: {e}")
                continue
        
        if agent:
            agent.bins_data = repo.get_bins()
        
        # UPDATE TRUCK POSITIONS AND ROUTES BASED ON SIMULATION TIME
        trucks = repo.get_trucks()
        for truck in trucks:
            try:
                if truck.get('status') in ['traveling', 'on_route', 'collecting', 'returning']:
                    truck_updated = update_truck_simulation_state(truck, time_delta, repo, agent)
                    if truck_updated:
                        repo.update_truck(truck['id'], truck_updated)
            except Exception as e:
                print(f"⌨ Error updating truck {truck.get('id', 'unknown')}: {e}")
        
        # Get traffic info
        traffic_info = {}
        if agent:
            tm = getattr(agent, 'traffic_manager', None)
            if tm is not None:
                config = Config()
                start_hour = config.SIMULATION_START_HOUR
                current_time_min = (start_hour * 60) + (simulation_time // 60)
                current_hour = (current_time_min // 60) % 24
                
                traffic_info = {
                    'current_density': tm.get_density_at_time(current_time_min),
                    'current_hour': current_hour,
                    'time_of_day': f"{current_hour:02d}:{(current_time_min % 60):02d}",
                    'traffic_level': 'Heavy' if tm.get_density_at_time(current_time_min) > 5 else 
                                    'Moderate' if tm.get_density_at_time(current_time_min) > 2 else 'Light'
                }
        
        # Get current collection queue from agent
        collection_queue_ids = []
        if agent and hasattr(agent, 'collection_queue'):
            collection_queue_ids = list(agent.collection_queue)
        
        return jsonify({
            "status": "success",
            "bins": repo.get_bins(),
            "bins_hit_threshold": bins_that_hit_threshold,
            "updated_urgencies": {},
            "traffic_info": traffic_info,
            "reserved_bins": list(agent.reserved_bins) if agent else [],
            "waiting_assignments": len(agent.waiting_assignments) if agent else 0,
            "schedule_dispatches": schedule_dispatches,
            "collection_queue": collection_queue_ids,
            "message": f"Simulation step completed ({time_delta}s)"
        })
        
    except Exception as e:
        print(f"⌨ Simulation step error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/route', methods=['POST'])
def get_route():
    """Get OSRM route between two points"""
    try:
        data = request.json
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid or missing JSON body"}), 400
        app = cast(Any, current_app)
        service = app.routing_service
        
        route_info = service.get_route_with_waypoints(
            data['from_lat'], data['from_lng'],
            data['to_lat'], data['to_lng']
        )
        
        return jsonify({
            "status": "success",
            "route": route_info
        })
        
    except Exception as e:
        print(f"⚠ Route calculation error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500