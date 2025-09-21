from flask import Blueprint, jsonify, request, current_app
from config.settings import Config

bp = Blueprint('simulation', __name__, url_prefix='/api')

@bp.route('/start_simulation', methods=['POST'])
def start_simulation():
    """Start simulation"""
    try:
        agent = current_app.agent
        repo = current_app.system_repository
        
        if not agent or not repo.get_bins() or not repo.get_depots():
            return jsonify({
                "status": "error",
                "message": "Need at least one depot and bins to start simulation"
            }), 400
        
        print("Starting simulation...")
        agent.bins_data = repo.get_bins()
        
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
        time_delta = data.get('time_delta', 1)
        simulation_time = data.get('simulation_time', 7)
        
        agent = current_app.agent
        repo = current_app.system_repository
        schedule_service = current_app.schedule_service
        
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
        
        # Get traffic info
        traffic_info = {}
        if agent and hasattr(agent, 'traffic_manager'):
            config = Config()
            start_hour = config.SIMULATION_START_HOUR
            current_time_min = (start_hour * 60) + (simulation_time // 60)
            current_hour = (current_time_min // 60) % 24
            
            traffic_info = {
                'current_density': agent.traffic_manager.get_density_at_time(current_time_min),
                'current_hour': current_hour,
                'time_of_day': f"{current_hour:02d}:{(current_time_min % 60):02d}",
                'traffic_level': 'Heavy' if agent.traffic_manager.get_density_at_time(current_time_min) > 5 else 
                                'Moderate' if agent.traffic_manager.get_density_at_time(current_time_min) > 2 else 'Light'
            }
        
        # Update clusters if needed
        clusters_data = {}
        if len(bins) >= 2 and agent:
            clusters = agent.get_or_create_clusters(bins)
            for cluster_id, cluster_bins in clusters.items():
                for bin_data in cluster_bins:
                    clusters_data[bin_data['id']] = [b['id'] for b in cluster_bins]
        
        return jsonify({
            "status": "success",
            "bins": repo.get_bins(),
            "bins_hit_threshold": bins_that_hit_threshold,
            "updated_urgencies": {},
            "traffic_info": traffic_info,
            "clusters": clusters_data,
            "reserved_bins": list(agent.reserved_bins) if agent else [],
            "waiting_assignments": len(agent.waiting_assignments) if agent else 0,
            "schedule_dispatches": schedule_dispatches,
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
        service = current_app.routing_service
        
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