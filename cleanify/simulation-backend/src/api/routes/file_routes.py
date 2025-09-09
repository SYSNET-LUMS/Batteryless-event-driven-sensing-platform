from flask import Blueprint, jsonify, request, current_app

bp = Blueprint('files', __name__, url_prefix='/api')

@bp.route('/save_system', methods=['POST'])
def save_system():
    """Save current system state"""
    try:
        system_state = request.json
        result = current_app.file_service.save_system(system_state)
        
        print(f"System saved to: {result['filepath']}")
        return jsonify(result)
        
    except Exception as e:
        print(f"⚠ Save failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/load_system/<filename>', methods=['GET'])
def load_system(filename):
    """Load system state from file"""
    try:
        system_state = current_app.file_service.load_system(filename)
        
        if system_state is None:
            return jsonify({
                'status': 'error',
                'message': f'File not found: {filename}'
            }), 404
        
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
        files = current_app.file_service.get_saved_files()
        return jsonify({
            'status': 'success',
            'files': files
        })
        
    except Exception as e:
        print(f"⚠ Failed to get files list: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500