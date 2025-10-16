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
    """Handle bin reaching disposal threshold with proactive cluster optimization"""
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
        
        # Process with proactive cluster dispatch
        result = agent.handle_bin_reached_dt_with_cluster_optimization(
            trigger_bin, bins, trucks, current_time
        )
        
        return jsonify({
            "status": "success",
            "dispatch_decision": result
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

@bp.route('/check_urgent_bins', methods=['POST'])
def check_urgent_bins():
    """Check urgent bins and get cluster bins for collection"""
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
        
        # Get clusters
        clusters = agent.get_or_create_clusters(bins) if len(bins) >= 2 else {}
        
        # Find cluster bins
        cluster_bins = []
        for cluster_id, c_bins in clusters.items():
            if any(b['id'] == target_bin_id for b in c_bins):
                cluster_bins = c_bins
                break
        
        # Find truck capacity
        truck = next((t for t in trucks if t['id'] == truck_id), None)
        if not truck:
            return jsonify({"status": "success", "bins_to_collect": []})
        
        # Use agent's knapsack-based collection
        bins_to_collect = agent.collect_bins_from_cluster(
            target_bin,
            cluster_bins,
            truck['capacity'],
            current_load,
            simulation_time
        )
        
        # Include target bin
        result_bins = [target_bin]
        result_bins.extend(bins_to_collect)
        
        # Mark bins as assigned
        for bin_data in result_bins:
            agent.mark_bin_assigned(bin_data['id'])
        
        return jsonify({
            "status": "success",
            "bins_to_collect": result_bins,
            "cluster_size": len(cluster_bins)
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
        
        # If route started, also update proactive dispatch with bin assignments
        if status == 'route_started' and assigned_bins:
            # Update proactive dispatch using existing method
            # Provide full bins so service can map bin IDs to proper cluster IDs
            repo = current_app.system_repository
            all_bins = repo.get_bins() if hasattr(repo, 'get_bins') else []
            agent.proactive_dispatch.update_truck_assignments({
                truck_id: {
                    'status': status,
                    'assigned_bins': assigned_bins,
                    'simulation_time': simulation_time,
                    'all_bins': all_bins
                }
            })
        
        return jsonify({
            "status": "success",
            "message": f"Truck {truck_id} status updated to {status}"
        })
        
    except Exception as e:
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
