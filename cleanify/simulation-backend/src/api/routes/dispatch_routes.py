"""
Minimalist Dispatch Routes
Main dispatch endpoint: Traffic Filter -> VROOM -> Routes
"""

from flask import Blueprint, jsonify, request, current_app
from typing import Any, cast

bp = Blueprint('dispatch', __name__, url_prefix='/api')


@bp.route('/dispatch', methods=['POST'])
def dispatch_trucks():
    """
    Main dispatch endpoint: Traffic Filter -> VROOM -> Routes
    
    Request: { simulation_time: 0 }
    Response: { routes: [...], waiting: [...] }
    """
    try:
        data = request.json or {}
        simulation_time = data.get('simulation_time', 0)
        
        app = cast(Any, current_app)
        repo = app.system_repository
        traffic_service = app.traffic_service
        vroom_service = app.vroom_service
        
        # Get system state
        bins = repo.get_bins()
        trucks = [t for t in repo.get_trucks() if t.get('status') == 'idle']
        depots = repo.get_depots()
        
        if not bins or not trucks or not depots:
            return jsonify({
                'status': 'success',
                'routes': [],
                'waiting': [],
                'message': 'Insufficient system components'
            })
        
        depot = depots[0]
        
        # Step 1: Filter bins that need collection (above threshold)
        threshold_default = 80
        urgent_bins = [b for b in bins if b.get('fillLevel', 0) >= b.get('threshold', threshold_default)]
        
        if not urgent_bins:
            return jsonify({
                'status': 'success',
                'routes': [],
                'waiting': [],
                'message': 'No bins need collection'
            })
        
        # Step 2: Traffic filtering
        dispatch_now, wait_bins = traffic_service.filter_bins_for_dispatch(
            urgent_bins, simulation_time
        )
        
        # Step 3: VROOM optimization
        if dispatch_now:
            vroom_result = vroom_service.optimize_routes(dispatch_now, trucks, depot)
            
            if vroom_result['status'] == 'success':
                routes = vroom_result['routes']
            else:
                # Fallback: simple assignment
                routes = _simple_fallback(dispatch_now, trucks)
        else:
            routes = []
        
        return jsonify({
            'status': 'success',
            'routes': routes,
            'waiting': [b['id'] for b in wait_bins],
            'traffic_filtered': len(wait_bins),
            'dispatch_count': len(routes)
        })
        
    except Exception as e:
        print(f"⚠️ Dispatch error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


def _simple_fallback(bins: list, trucks: list) -> list:
    """Fallback if VROOM fails: one bin per truck"""
    routes = []
    for i, truck in enumerate(trucks):
        if i < len(bins):
            routes.append({
                'truck_id': truck['id'],
                'bin_ids': [bins[i]['id']],
                'distance': 0,
                'duration': 0
            })
    return routes
