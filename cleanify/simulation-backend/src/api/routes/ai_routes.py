from flask import Blueprint, jsonify, request, current_app

bp = Blueprint('ai', __name__, url_prefix='/api')

@bp.route('/ai_decision/<decision_type>', methods=['POST'])
def get_ai_decision(decision_type):
    """AI decision with coordination support"""
    try:
        agent = current_app.agent
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
        
        data['bins_data'] = available_bins
        data['trucks_data'] = trucks
        data['depots_data'] = repo.get_depots()
        data['simulation_time'] = data.get('simulation_time', 0)
        
        # Get coordinated routing decisions
        result = agent.get_ai_decision(decision_type, data)
        
        # Check for waiting trucks ready to dispatch
        if decision_type == "truck_routing":
            simulation_time = data.get('simulation_time', 0)
            ready_dispatches = agent.process_waiting_trucks(simulation_time)
            
            if ready_dispatches:
                print(f"🚛 {len(ready_dispatches)} trucks ready for dispatch after waiting")
                result.extend(ready_dispatches)
        
        return jsonify({
            "status": "success",
            "decision_type": decision_type,
            "result": result
        })
        
    except Exception as e:
        print(f"⚠️ AI decision failed for {decision_type}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/check_urgent_bins', methods=['POST'])
def check_urgent_bins():
    """Check urgent bins and get cluster bins for collection"""
    try:
        agent = current_app.agent
        repo = current_app.system_repository
        
        if not agent:
            return jsonify({"status": "error", "message": "Agent not available"}), 400
        
        data = request.json
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