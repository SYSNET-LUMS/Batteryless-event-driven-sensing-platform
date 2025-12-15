from flask import Blueprint, jsonify, request, current_app
from typing import Any, cast
import threading

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

@bp.route('/load_system/<path:filename>', methods=['GET'])
def load_system(filename):
    """Load system state from file"""
    try:
        app = cast(Any, current_app)
        # Normalize filename to prevent directory traversal and bad encodings
        safe_name = filename.strip()
        if '/' in safe_name or safe_name.startswith('..'):
            return jsonify({
                'status': 'error',
                'message': 'Invalid filename'
            }), 400

        system_state = app.file_service.load_system(safe_name)
        if system_state is None:
            return jsonify({
                'status': 'error',
                'message': f'File not found: {safe_name}'
            }), 404
        
        # Restore system state in repository
        repo = app.system_repository
        repo.set_state(system_state)
        _apply_dynamic_thresholds(app, repo.get_bins())
        # Trigger async distance matrix rebuild unless explicitly disabled
        rebuild = request.args.get('rebuild', 'true').lower() in ('1', 'true', 'yes')
        if rebuild:
            _trigger_async_rebuild(app)
        
        print(f"System loaded from: {safe_name}")
        return jsonify({
            'status': 'success',
            'systemState': system_state,
            'filename': safe_name,
            'rebuild': rebuild
        })
        
    except Exception as e:
        print(f"⚠ Load failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


_rebuild_lock = threading.Lock()
_rebuild_in_progress = False

def _trigger_async_rebuild(app) -> None:
    global _rebuild_in_progress
    if _rebuild_in_progress:
        return
    def worker():
        global _rebuild_in_progress
        with _rebuild_lock:
            _rebuild_in_progress = True
        try:
            # Acquire the real Flask app object and push app context
            from flask import current_app as flask_current_app
            try:
                app_obj = flask_current_app._get_current_object()
            except Exception:
                app_obj = app
            if not app_obj:
                return
            with app_obj.app_context():
                service = getattr(app_obj, 'distance_matrix_service', None)
                if not service:
                    return
                repo = app_obj.system_repository
                service.build_matrices(repo.get_bins(), repo.get_depots(), force=True)
        finally:
            with _rebuild_lock:
                _rebuild_in_progress = False
    t = threading.Thread(target=worker, daemon=True)
    t.start()

@bp.route('/distance_matrix/status', methods=['GET'])
def distance_matrix_status():
    app = cast(Any, current_app)
    service = getattr(app, 'distance_matrix_service', None)
    summary = getattr(service, 'last_build_summary', {}) if service else {}
    return jsonify({
        'inProgress': _rebuild_in_progress,
        'summary': summary
    })

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


def _apply_dynamic_thresholds(app, bins) -> None:
    service = getattr(app, 'dynamic_threshold_service', None)
    if not service or not bins:
        return
    service.apply_to_bins(bins)