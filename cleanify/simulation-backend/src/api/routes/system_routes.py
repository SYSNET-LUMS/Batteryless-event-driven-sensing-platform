from flask import Blueprint, jsonify, request, current_app

bp = Blueprint('system', __name__, url_prefix='/api')

@bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "active",
        "message": "Minimalist backend running",
        "version": "2.0-minimalist"
    })

@bp.route('/initialize', methods=['POST'])
def initialize_system():
    """Initialize the waste collection system"""
    try:
        current_app.system_repository.clear_all()
        distance_service = getattr(current_app, 'distance_matrix_service', None)
        if distance_service:
            distance_service.clear()
        # No need to reset singleton agent here; use AgentManager.reset_agent() if needed
        warning_msg = "System initialized. WARNING: All schedules and system state have been cleared. Do not call this after loading a system file if you want to keep schedules."
        return jsonify({"status": "success", "message": warning_msg})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/osrm_debug', methods=['GET'])
def osrm_debug():
    """Return OSRM instrumentation statistics"""
    try:
        # Try to access a shared OSRM service reference. If not present, create temp.
        osrm_service = getattr(current_app, 'osrm_service', None)
        if not osrm_service:
            # Fallback: attempt to reach through agent or services if attached
            agent = getattr(current_app, 'agent', None)
            if agent and hasattr(agent, 'decision_service'):
                osrm_service = getattr(agent.decision_service.optimization_service, 'osrm_service', None)
        if not osrm_service:
            return jsonify({"status": "error", "message": "OSRMService not available"}), 404
        stats = osrm_service.stats
        return jsonify({"status": "success", "osrm_stats": stats, "cache_sizes": {
            "route_cache": len(osrm_service._route_cache),
            "distance_cache": len(osrm_service._distance_cache),
            "travel_cache": len(osrm_service._travel_cache)
        }})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/osrm_debug/reset', methods=['POST'])
def osrm_debug_reset():
    try:
        osrm_service = getattr(current_app, 'osrm_service', None)
        if not osrm_service:
            return jsonify({"status": "error", "message": "OSRMService not available"}), 404
        osrm_service.reset_stats()
        return jsonify({"status": "success", "message": "OSRM stats reset"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route('/distance_matrix/status', methods=['GET'])
def distance_matrix_status():
    """Expose the current distance matrix cache status for debugging."""
    service = getattr(current_app, 'distance_matrix_service', None)
    if not service:
        return jsonify({"status": "error", "message": "DistanceMatrixService unavailable"}), 503

    summary = service.last_build_summary or {"status": "empty"}
    cache_sizes = {
        "depots": len(service.depot_to_bin),
        "bins": len(service.bin_to_depot),
        "depot_to_bin_entries": sum(len(v) for v in service.depot_to_bin.values()),
        "bin_to_bin_entries": sum(len(v) for v in service.bin_to_bin.values()),
    }
    return jsonify({
        "status": "success",
        "summary": summary,
        "cache_sizes": cache_sizes,
    })