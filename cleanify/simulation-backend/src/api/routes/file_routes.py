from flask import Blueprint, jsonify, request, current_app
from typing import Any, cast
from services.agent_manager import get_agent

bp = Blueprint('files', __name__, url_prefix='/api')

@bp.route('/save_system', methods=['POST'])
def save_system():
    """Save current system state"""
    try:
        # Always get latest state from repository, not just request
        app = cast(Any, current_app)
        repo = app.system_repository
        system_state = repo.get_state()
        result = app.file_service.save_system(system_state)
        print(f"System saved to: {result['filepath']}")
        return jsonify(result)
    except Exception as e:
        print(f"⚠ Save failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/load_system/<filename>', methods=['GET'])
def load_system(filename):
    """Load system state from file"""
    try:
        app = cast(Any, current_app)
        system_state = app.file_service.load_system(filename)
        if system_state is None:
            return jsonify({
                'status': 'error',
                'message': f'File not found: {filename}'
            }), 404
        # Restore system state in repository
        repo = app.system_repository
        repo.set_state(system_state)
        
        # Update singleton agent with latest state and refresh distance cache
        agent = get_agent()
        if agent:
            agent.refresh_system_state(repo.get_bins(), repo.get_depots())
            print(f"🔄 Updated agent state and warmed distance cache due to system load (agent_id={id(agent)})")
        
        print(f"System loaded from: {filename}")
        return jsonify({
            'status': 'success',
            'systemState': system_state,
            'filename': filename
        })
        
    except Exception as e:
        print(f"⚠ Load failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/saved_files', methods=['GET'])
def get_saved_files():
    """Get list of saved files"""
    try:
        app = cast(Any, current_app)
        files = app.file_service.get_saved_files()
        return jsonify({
            'status': 'success',
            'files': files
        })
        
    except Exception as e:
        print(f"⚠ Failed to get files list: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500