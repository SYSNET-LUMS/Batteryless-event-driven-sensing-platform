from flask import Blueprint, jsonify, request, current_app

bp = Blueprint('ai', __name__, url_prefix='/api')
from services.agent_manager import get_agent

@bp.route('/ai_decision/<decision_type>', methods=['POST'])
def get_ai_decision(decision_type):
    """AI decision with coordination support"""
    try:
        agent = get_agent()
        repo = current_app.system_repository
        
        if not agent:
            return jsonify({"status": "error", "message": "Agent not available"}), 400
        
        data = request.get_json() or {}
        
        # Reset assignments for new routing cycle
        if decision_type == "truck_routing":
            agent.reset_assignments()
        
        # Check if system has data
        bins = repo.get_bins()
        trucks = repo.get_trucks()
        
        if not bins or not trucks:
            return jsonify({
                "status": "success",
                "result": [],
                "message": "No bins or trucks available"
            })
        
        # Filter out already assigned bins
        available_bins = [b for b in bins if not agent.is_bin_assigned(b['id'])]
        
        # Filter out reserved trucks (for upcoming scheduled dispatches)
        schedule_service = getattr(current_app, 'schedule_service', None)
        reserved_trucks = []
        if schedule_service:
            try:
                schedules = repo.get_schedules()
                simulation_time = data.get('simulation_time', 0)
                reserved_trucks = schedule_service.get_reserved_trucks(schedules, simulation_time)
            except Exception as e:
                print(f"⚠️ Error checking truck reservations: {e}")
        
        # Filter out reserved trucks from available trucks
        available_trucks = [t for t in trucks if t['id'] not in reserved_trucks]
        
        data['bins_data'] = available_bins
        data['trucks_data'] = available_trucks
        data['depots_data'] = repo.get_depots()
        data['simulation_time'] = data.get('simulation_time', 0)
        
        # Get coordinated routing decisions
        result = agent.get_ai_decision(decision_type, data)
        
        # Check for waiting trucks ready to dispatch
        if decision_type == "truck_routing":
            simulation_time = data.get('simulation_time', 0)
            ready_dispatches = agent.process_waiting_trucks(simulation_time)
            
            if ready_dispatches:
                result.extend(ready_dispatches)
        
        return jsonify({
            "status": "success",
            "decision_type": decision_type,
            "result": result
        })
        
    except Exception as e:
        print(f"⚠️ AI decision failed for {decision_type}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/bin_reached_dt', methods=['POST'])
def handle_bin_reached_dt():
    """Handle bin reaching disposal threshold using pure distance dispatch."""
    try:
        agent = get_agent()
        repo = current_app.system_repository
        
        if not agent:
            return jsonify({"status": "error", "message": "Agent not available"}), 400
        
        data = request.json or {}
        trigger_bin_id = data.get('bin_id')
        current_time = data.get('simulation_time', 0)
        
        if not trigger_bin_id:
            return jsonify({"status": "error", "message": "bin_id required"}), 400
        
        # Get system data
        bins = repo.get_bins()
        trucks = repo.get_trucks()
        
        # Find the trigger bin
        trigger_bin = next((b for b in bins if b['id'] == trigger_bin_id), None)
        if not trigger_bin:
            return jsonify({"status": "error", "message": "Bin not found"}), 404
        
        plan = agent.handle_bin_reached_dt(trigger_bin, bins, trucks, current_time)
        return jsonify({
            "status": "success",
            "mode": "distance_dispatch",
            "dispatch_decision": plan
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/proactive_dispatch_status', methods=['GET'])
def get_proactive_dispatch_status():
    """Get status of proactive dispatch system"""
    try:
        agent = get_agent()
        
        if not agent:
            return jsonify({"status": "error", "message": "Agent not available"}), 400
        
        status = agent.get_proactive_dispatch_status()
        
        return jsonify({
            "status": "success",
            "proactive_dispatch_status": status
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/dispatch/bin/<bin_id>', methods=['POST'])
def plan_dispatch_for_bin(bin_id: str):
    """Direct distance-dispatch planning API for operator tooling."""
    try:
        config = current_app.config_obj
        dispatch_planner = getattr(current_app, 'dispatch_planner', None)
        if not config.USE_DISTANCE_DISPATCH or not dispatch_planner:
            return jsonify({
                "status": "error",
                "message": "Distance-based dispatch disabled"
            }), 400

        payload = request.get_json(silent=True) or {}
        simulation_time = payload.get('simulation_time', 0)
        plan = dispatch_planner.plan_dispatch_for_bin(bin_id, simulation_time)
        http_status = 200 if plan.get('status') == 'success' else 400
        return jsonify({
            "status": "success" if plan.get('status') == 'success' else "error",
            "mode": "distance_dispatch",
            "dispatch_decision": plan
        }), http_status

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bp.route('/check_urgent_bins', methods=['POST'])
def check_urgent_bins():
    """Return distance-ranked bins to collect for a truck/target bin combo."""
    try:
        agent = get_agent()
        repo = current_app.system_repository
        
        if not agent:
            return jsonify({"status": "error", "message": "Agent not available"}), 400
        
        data = request.json or {}
        truck_id = data.get('truck_id')
        target_bin_id = data.get('target_bin_id')
        current_load = data.get('current_load', 0)
        simulation_time = data.get('simulation_time', 0)
        
        bins = repo.get_bins()
        trucks = repo.get_trucks()
        
        # Find target bin
        target_bin = next((b for b in bins if b['id'] == target_bin_id), None)
        if not target_bin:
            return jsonify({"status": "success", "bins_to_collect": []})

        # Use distance planner through agent helper
        plan = agent.plan_distance_dispatch_for_bin(target_bin_id, simulation_time)
        selected_bins = plan.get('selected_bins') or []
        bins_by_id = {b['id']: b for b in bins}
        bins_to_collect = [bins_by_id[bin_id] for bin_id in selected_bins if bin_id in bins_by_id]

        # Optionally mark bins as assigned to maintain compatibility
        for bin_data in bins_to_collect:
            agent.mark_bin_assigned(bin_data['id'])
        
        return jsonify({
            "status": "success",
            "mode": "distance_dispatch",
            "bins_to_collect": bins_to_collect,
            "dispatch_decision": plan
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/update_truck_assignment', methods=['POST'])
def update_truck_assignment():
    """Update truck assignment status for proactive dispatch tracking"""
    try:
        agent = get_agent()
        
        if not agent:
            return jsonify({"status": "error", "message": "Agent not available"}), 400
        
        data = request.json or {}
        truck_id = data.get('truck_id')
        status = data.get('status')
        assigned_bins = data.get('assigned_bins', [])
        simulation_time = data.get('simulation_time', 0)
        
        if not truck_id or not status:
            return jsonify({"status": "error", "message": "truck_id and status required"}), 400
        
        # Update truck assignment status in agent
        agent.update_truck_assignment_status(truck_id, status)
        
        # For legacy compatibility we simply log assignments; distance dispatch has no
        # cluster or proactive locking state to update.
        if status == 'route_started' and assigned_bins:
            print(f"🚛 Truck {truck_id} started route for bins {assigned_bins} at t={simulation_time}")
        
        return jsonify({
            "status": "success",
            "message": f"Truck {truck_id} status updated to {status}"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/bins_collected', methods=['POST'])
def bins_collected():
    """
    Notify backend that bins have been collected by a truck.
    This updates the proactive dispatch tracking to prevent duplicate dispatches.
    """
    try:
        agent = get_agent()
        if not agent:
            return jsonify({"status": "error", "message": "Agent not available"}), 400
        
        data = request.json or {}
        truck_id = data.get('truck_id')
        collected_bin_ids = data.get('collected_bin_ids', [])
        simulation_time = data.get('simulation_time', 0)
        
        if not truck_id or not collected_bin_ids:
            return jsonify({"status": "error", "message": "truck_id and collected_bin_ids required"}), 400
        
        # Remove collected bins from collection queue
        if hasattr(agent, 'collection_queue'):
            original_size = len(agent.collection_queue)
            agent.collection_queue = [bid for bid in agent.collection_queue if bid not in collected_bin_ids]
            removed_count = original_size - len(agent.collection_queue)
            if removed_count > 0:
                print(f"🗑️ Removed {removed_count} collected bins from queue: {collected_bin_ids}")
        
        print(f"✅ Truck {truck_id} collected bins: {collected_bin_ids}")
        
        return jsonify({
            "status": "success",
            "message": f"Marked {len(collected_bin_ids)} bins as collected by {truck_id}"
        })
        
    except Exception as e:
        print(f"⚠️ Error marking bins as collected: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/collection_queue', methods=['GET'])
def get_collection_queue():
    """Get current collection queue from agent"""
    try:
        agent = get_agent()
        if not agent:
            return jsonify({"status": "error", "message": "Agent not available"}), 400
        # Return full bin objects for frontend display
        repo = current_app.system_repository
        all_bins = {b['id']: b for b in repo.get_bins()}
        queue_ids = agent.collection_queue if hasattr(agent, 'collection_queue') else []
        queue_bins = [all_bins.get(bin_id, {"id": bin_id, "fillLevel": 0}) for bin_id in queue_ids]
        return jsonify({
            "status": "success",
            "collection_queue": queue_bins
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500        
