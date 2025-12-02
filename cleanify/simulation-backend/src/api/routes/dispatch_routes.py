"""
Minimalist Dispatch Routes
Main dispatch endpoint: Traffic Filter -> VROOM -> Routes
Prevents duplicate dispatching by updating system state immediately
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
        # Also exclude bins already being processed
        threshold_default = 80
        urgent_bins = [
            b for b in bins 
            if b.get('fillLevel', 0) >= b.get('threshold', threshold_default)
            and not b.get('dispatched', False)  # Skip already dispatched bins
        ]
        
        if not urgent_bins:
            return jsonify({
                'status': 'success',
                'routes': [],
                'waiting': [],
                'message': 'No bins need collection'
            })
        
        # Step 2: Smart Batching - Prevent aggressive 1-bin dispatches
        should_dispatch, batch_reason = _should_dispatch_batch(urgent_bins, trucks)
        
        if not should_dispatch:
            return jsonify({
                'status': 'success',
                'routes': [],
                'waiting': [b['id'] for b in urgent_bins],
                'message': f'Accumulating load: {batch_reason}',
                'batching': True
            })
        
        print(f"📦 Smart Batch: {batch_reason}")
        
        # Step 3: Traffic filtering
        dispatch_now, wait_bins = traffic_service.filter_bins_for_dispatch(
            urgent_bins, simulation_time
        )
        
        # Step 4: VROOM optimization
        routes = []
        if dispatch_now:
            vroom_result = vroom_service.optimize_routes(dispatch_now, trucks, depot)
            
            if vroom_result['status'] == 'success':
                routes = vroom_result['routes']
            else:
                # Fallback: simple assignment
                routes = _simple_fallback(dispatch_now, trucks)
        
        # Step 5: CRITICAL - Update system state immediately to prevent duplicate dispatch
        if routes:
            _update_dispatch_state(repo, routes)
            print(f"✅ Dispatched {len(routes)} trucks, updated system state")
        
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


def _update_dispatch_state(repo, routes: list):
    """
    Update truck and bin status immediately after dispatch to prevent duplicates
    
    Args:
        repo: SystemRepository instance
        routes: List of route dictionaries with truck_id and bin_ids
    """
    for route in routes:
        truck_id = route['truck_id']
        bin_ids = route['bin_ids']
        
        # Update truck status to 'dispatching' (frontend will change to 'traveling')
        trucks = repo.get_trucks()
        for truck in trucks:
            if truck['id'] == truck_id:
                truck['status'] = 'dispatching'
                truck['assigned_bins'] = bin_ids
                repo.update_truck(truck_id, truck)
                print(f"   🚛 {truck_id}: idle → dispatching")
                break
        
        # Mark bins as dispatched to prevent re-selection
        bins = repo.get_bins()
        for bin_data in bins:
            if bin_data['id'] in bin_ids:
                bin_data['dispatched'] = True
                bin_data['assigned_truck'] = truck_id
                repo.update_bin(bin_data['id'], bin_data)
                print(f"   🗑️  {bin_data['id']}: marked as dispatched")


def _should_dispatch_batch(urgent_bins: list, trucks: list) -> tuple[bool, str]:
    """
    Smart Batching Logic: Prevent aggressive 1-bin dispatches
    
    Decision Rule:
    - DISPATCH if critical bins exist (>90% fill)
    - DISPATCH if total waste volume > 50% of avg truck capacity
    - WAIT otherwise (accumulate more bins)
    
    Args:
        urgent_bins: Bins above threshold (80%)
        trucks: Available trucks
        
    Returns:
        (should_dispatch: bool, reason: str)
    """
    if not urgent_bins or not trucks:
        return False, "No bins or trucks available"
    
    # Check for critical bins (>90% fill)
    CRITICAL_THRESHOLD = 90
    critical_bins = [b for b in urgent_bins if b.get('fillLevel', 0) >= CRITICAL_THRESHOLD]
    
    if critical_bins:
        return True, f"{len(critical_bins)} critical bins (>90% full)"
    
    # Calculate total waste volume in urgent bins
    total_waste_volume = sum(b.get('fillLevel', 0) for b in urgent_bins)
    
    # Calculate average truck capacity
    capacities = [t.get('capacity', 100) for t in trucks]
    avg_truck_capacity = sum(capacities) / len(capacities) if capacities else 100
    
    # Dispatch if total waste > 50% of average truck capacity
    BATCH_THRESHOLD = 0.5
    waste_ratio = total_waste_volume / avg_truck_capacity
    
    if waste_ratio >= BATCH_THRESHOLD:
        return True, f"Waste volume {total_waste_volume:.1f}L >= {BATCH_THRESHOLD*100}% of truck capacity ({avg_truck_capacity:.1f}L)"
    
    return False, f"Waiting for more bins ({total_waste_volume:.1f}L < {BATCH_THRESHOLD*100}% of {avg_truck_capacity:.1f}L)"


@bp.route('/bins_collected', methods=['POST'])
def bins_collected():
    """
    Handle bin collection completion
    
    Request: { "truck_id": "TRUCK_1", "collected_bin_ids": ["BIN_1", "BIN_2"] }
    Response: { "status": "success", "updated_bins": 2 }
    """
    try:
        data = request.json or {}
        truck_id = data.get('truck_id')
        collected_bin_ids = data.get('collected_bin_ids', [])
        
        if not truck_id or not collected_bin_ids:
            return jsonify({
                'status': 'error',
                'message': 'truck_id and collected_bin_ids required'
            }), 400
        
        app = cast(Any, current_app)
        repo = app.system_repository
        
        # Reset collected bins
        bins = repo.get_bins()
        updated_count = 0
        truck_load_freed = 0
        
        for bin_data in bins:
            if bin_data['id'] in collected_bin_ids:
                # Store bin capacity before reset
                bin_capacity = bin_data.get('fillLevel', 0)
                truck_load_freed += bin_capacity
                
                # Reset bin state
                bin_data['fillLevel'] = 0
                bin_data['dispatched'] = False
                bin_data['assigned_truck'] = None
                repo.update_bin(bin_data['id'], bin_data)
                updated_count += 1
                print(f"✅ Collected {bin_data['id']}: fillLevel → 0, dispatched → False")
        
        # Update truck current_load
        trucks = repo.get_trucks()
        for truck in trucks:
            if truck['id'] == truck_id:
                current_load = truck.get('current_load', 0)
                new_load = max(0, current_load - truck_load_freed)
                truck['current_load'] = new_load
                repo.update_truck(truck_id, truck)
                print(f"🚛 {truck_id}: load {current_load} → {new_load}")
                break
        
        return jsonify({
            'status': 'success',
            'updated_bins': updated_count,
            'truck_load_freed': truck_load_freed
        })
        
    except Exception as e:
        print(f"⚠️ bins_collected error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bp.route('/update_truck_status', methods=['POST'])
def update_truck_status():
    """
    Update truck status and release unvisited bins if truck goes idle
    
    Request: { "truck_id": "TRUCK_1", "status": "idle" }
    Response: { "status": "success", "released_bins": 2 }
    """
    try:
        data = request.json or {}
        truck_id = data.get('truck_id')
        new_status = data.get('status')
        
        if not truck_id or not new_status:
            return jsonify({
                'status': 'error',
                'message': 'truck_id and status required'
            }), 400
        
        app = cast(Any, current_app)
        repo = app.system_repository
        
        # Update truck status
        trucks = repo.get_trucks()
        truck_found = False
        
        for truck in trucks:
            if truck['id'] == truck_id:
                old_status = truck.get('status', 'unknown')
                truck['status'] = new_status
                repo.update_truck(truck_id, truck)
                truck_found = True
                print(f"🚛 {truck_id}: {old_status} → {new_status}")
                break
        
        if not truck_found:
            return jsonify({
                'status': 'error',
                'message': f'Truck {truck_id} not found'
            }), 404
        
        # CRITICAL: If truck goes idle, release any bins still assigned to it
        # This fixes the capacity bug where unvisited bins remain locked
        released_bins = 0
        if new_status == 'idle':
            bins = repo.get_bins()
            for bin_data in bins:
                if bin_data.get('assigned_truck') == truck_id and bin_data.get('dispatched', False):
                    # This bin was assigned but never collected
                    bin_data['dispatched'] = False
                    bin_data['assigned_truck'] = None
                    repo.update_bin(bin_data['id'], bin_data)
                    released_bins += 1
                    print(f"   🔓 Released {bin_data['id']} (was assigned to {truck_id})")
        
        return jsonify({
            'status': 'success',
            'truck_id': truck_id,
            'new_status': new_status,
            'released_bins': released_bins
        })
        
    except Exception as e:
        print(f"⚠️ update_truck_status error: {e}")
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
