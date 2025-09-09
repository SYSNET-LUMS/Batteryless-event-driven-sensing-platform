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
        return jsonify({"status": "success", "message": "System initialized"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500