from flask import Blueprint, jsonify, request, current_app

bp = Blueprint('system', __name__, url_prefix='/api')

@bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "success",
        "message": "Simplified backend running",
        "agent_ready": current_app.agent is not None,
        "version": "2.0-simplified"
    })

@bp.route('/initialize', methods=['POST'])
def initialize_system():
    """Initialize the waste collection system"""
    try:
        current_app.system_repository.clear_all()
        current_app.agent = None
        warning_msg = "System initialized. WARNING: All schedules and system state have been cleared. Do not call this after loading a system file if you want to keep schedules."
        return jsonify({"status": "success", "message": warning_msg})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500