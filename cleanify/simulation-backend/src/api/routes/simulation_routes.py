"""
Minimalist Simulation Routes
Simple time progression and bin fill level updates
"""

from flask import Blueprint, request, jsonify, current_app
from typing import Any, cast

bp = Blueprint('simulation', __name__, url_prefix='/api')


@bp.route('/start_simulation', methods=['POST'])
def start_simulation():
    """Initialize simulation state"""
    try:
        app = cast(Any, current_app)
        repo = app.system_repository
        
        if not repo.get_bins() or not repo.get_depots():
            return jsonify({
                'status': 'error',
                'message': 'Need bins and depot to start'
            }), 400
        
        print("✅ Simulation started")
        
        return jsonify({
            'status': 'success',
            'message': 'Simulation ready'
        })
        
    except Exception as e:
        print(f"⚠️ Simulation start error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bp.route('/simulation_step', methods=['POST'])
def simulation_step():
    """Update bin fill levels only (no agents, no complex logic)"""
    try:
        data = request.json
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON body"}), 400
        
        time_delta = data.get('time_delta', 1)
        
        app = cast(Any, current_app)
        repo = app.system_repository
        bins = repo.get_bins()
        
        # Update fill levels
        for bin_item in bins:
            hours_passed = time_delta / 3600
            increase = bin_item.get('fillRate', 3.5) * hours_passed
            current_fill = bin_item.get('fillLevel', 0)
            bin_item['fillLevel'] = min(100, current_fill + increase)
            repo.update_bin(bin_item['id'], bin_item)
        
        return jsonify({
            'status': 'success',
            'bins': repo.get_bins(),
            'message': f'Simulation step completed ({time_delta}s)'
        })
        
    except Exception as e:
        print(f"⚠️ Simulation step error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bp.route('/route', methods=['POST'])
def get_route():
    """Get OSRM route between two points"""
    try:
        data = request.json
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON body"}), 400
        
        app = cast(Any, current_app)
        service = app.routing_service
        
        route_info = service.get_route_with_waypoints(
            data['from_lat'], data['from_lng'],
            data['to_lat'], data['to_lng']
        )
        
        return jsonify({
            'status': 'success',
            'route': route_info
        })
        
    except Exception as e:
        print(f"⚠️ Route error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500