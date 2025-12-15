"""
Unified Global Optimization Dispatch (Refactored)
Send ALL bins to VROOM with priorities + time windows
Prevents duplicate dispatching by updating system state immediately
"""

from flask import Blueprint, jsonify, request, current_app
from typing import Any, cast, Dict, Optional

from utils.distance import calculate_haversine_distance

bp = Blueprint('dispatch', __name__, url_prefix='/api')

SINGLE_TRIGGER_MAX_BINS = 3
SINGLE_TRIGGER_RADIUS_MIN = 750.0  # meters
SINGLE_TRIGGER_RADIUS_MAX = 4000.0  # meters


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
        vroom_service = app.vroom_service
        dt_service = getattr(app, 'dynamic_threshold_service', None)
        distance_service = getattr(app, 'distance_matrix_service', None)
        
        # Get system state
        bins = repo.get_bins()
        idle_trucks = [t for t in repo.get_trucks() if t.get('status') == 'idle']
        depots = repo.get_depots()
        
        if not bins or not idle_trucks or not depots:
            return jsonify({
                'status': 'success',
                'routes': [],
                'waiting': [b['id'] for b in bins],
                'message': 'No idle trucks available'
            })
        
        depot = depots[0]
        if dt_service:
            # Annotate all bins so downstream consumers (frontend/tests) see DT
            dt_service.apply_to_bins(bins)
        
        # UNIFIED GLOBAL OPTIMIZATION: Get all non-dispatched bins
        # Filter bins that are neither dispatched nor assigned to active trucks
        undispatch_bins = [
            b for b in bins 
            if not b.get('dispatched', False) and not b.get('assigned_truck')
        ]
        
        print(f"📊 Dispatch check: {len(bins)} total bins, {len(undispatch_bins)} available for dispatch")
        for b in bins:
            if b.get('dispatched') or b.get('assigned_truck'):
                print(f"   🔒 {b['id']}: dispatched={b.get('dispatched')}, assigned_truck={b.get('assigned_truck')}")
        
        if not undispatch_bins:
            return jsonify({
                'status': 'success',
                'routes': [],
                'waiting': [],
                'message': 'No undispatched bins available'
            })
        
        # Step 1: Calculate urgency metrics for each bin
        for b in undispatch_bins:
            _calculate_bin_urgency(b, depot, simulation_time)
        
        # Step 2: Classify bins by urgency (for predictive dispatch)
        critical_bins, near_threshold_bins, low_urgency_bins = _classify_bins_by_urgency(
            undispatch_bins, simulation_time
        )
        
        # Step 3: Unified dispatch decision
        should_dispatch = _should_dispatch_unified(
            critical_bins, near_threshold_bins, idle_trucks
        )
        
        if not should_dispatch:
            waiting_ids = [b['id'] for b in undispatch_bins]
            return jsonify({
                'status': 'success',
                'routes': [],
                'waiting': waiting_ids,
                'message': f'Accumulating. Critical: {len(critical_bins)}, Near: {len(near_threshold_bins)}, Low: {len(low_urgency_bins)}',
                'batching': True,
                'bin_classification': {
                    'critical': len(critical_bins),
                    'near_threshold': len(near_threshold_bins),
                    'low_urgency': len(low_urgency_bins)
                }
            })

        # Step 4: Select bins and trucks for the current dispatch wave
        active_bins = _select_active_dispatch_bins(
            undispatch_bins, critical_bins, depot
        )
        active_trucks = _select_trucks_for_active_dispatch(
            idle_trucks, critical_bins, depot
        )

        if not active_bins or not active_trucks:
            waiting_ids = [b['id'] for b in undispatch_bins]
            return jsonify({
                'status': 'success',
                'routes': [],
                'waiting': waiting_ids,
                'message': 'No eligible bins or trucks after filtering'
            })

        active_bin_ids = {b.get('id') for b in active_bins if b.get('id')}
        active_critical_bins = [
            b for b in critical_bins
            if b.get('id') in active_bin_ids
        ]
        
        # Step 5: Ensure distance matrix is available before VROOM
        _ensure_distance_matrix(app, active_bins)
        proximity_routes = _build_proximity_routes(
            active_bins, active_trucks, depot, distance_service
        )
        
        # Step 6: GLOBAL VROOM OPTIMIZATION with selected bins
        routes = []
        if active_bins:
            vroom_result = vroom_service.optimize_routes_with_constraints(
                active_bins, active_trucks, depot, active_critical_bins, simulation_time
            )
            
            if vroom_result['status'] == 'success':
                routes = vroom_result['routes']
            else:
                print("⚠️ Falling back to proximity routes because VROOM failed")
                routes = proximity_routes

        if _should_use_proximity_routes(routes, proximity_routes, active_trucks):
            if routes != proximity_routes:
                print("♻️ Rebalancing routes using proximity heuristic")
            routes = proximity_routes
        
        # Step 6: Update system state IMMEDIATELY to prevent race conditions
        if routes:
            _update_dispatch_state(repo, routes)
            print(f"✅ Dispatched {len(routes)} trucks, marked bins as dispatched")
            for route in routes:
                print(f"   🚛 {route['truck_id']}: bins={route['bin_ids']}")
        
        return jsonify({
            'status': 'success',
            'routes': routes,
            'dispatch_count': len(routes),
            'bin_classification': {
                'critical': len(critical_bins),
                'near_threshold': len(near_threshold_bins),
                'low_urgency': len(low_urgency_bins)
            }
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
                break
        
        # Mark bins as dispatched to prevent re-selection
        bins = repo.get_bins()
        for bin_data in bins:
            if bin_data['id'] in bin_ids:
                bin_data['dispatched'] = True
                bin_data['assigned_truck'] = truck_id
                repo.update_bin(bin_data['id'], bin_data)


def _calculate_bin_urgency(bin_data: Dict, depot: Dict, simulation_time: float) -> None:
    """
    Calculate urgency metrics for a bin. Used by VROOM for priority weighting.
    """
    fill = bin_data.get('fillLevel', 0)
    capacity = bin_data.get('capacity', 500)
    rate = bin_data.get('fillRate', 1.0)
    
    # Time to overflow (hours)
    if rate > 0:
        remaining_capacity = (100 - fill) * capacity / 100
        time_to_overflow = remaining_capacity / rate
    else:
        time_to_overflow = float('inf')
    
    # Urgency score (0-100): higher = more urgent
    fill_score = (fill / 100) * 40  # 0-40 points
    rate_score = min(30, (rate / 10) * 30)  # 0-30 points
    
    if time_to_overflow <= 1:
        overflow_score = 30
    elif time_to_overflow <= 4:
        overflow_score = 20
    else:
        overflow_score = 10
    
    urgency_score = min(100, fill_score + rate_score + overflow_score)
    
    bin_data['urgency_score'] = urgency_score
    bin_data['time_to_overflow'] = time_to_overflow


def _classify_bins_by_urgency(bins: list, simulation_time: float) -> tuple:
    """
    Classify bins into urgency categories.
    Returns: (critical_bins, near_threshold_bins, low_urgency_bins)
    """
    critical = []
    near_threshold = []
    low_urgency = []
    
    for b in bins:
        fill = b.get('fillLevel', 0)
        time_overflow = b.get('time_to_overflow', float('inf'))
        threshold = _effective_threshold(b)
        near_threshold_floor = max(0.0, threshold - 5.0)

        if fill >= threshold or time_overflow < 1.0:
            critical.append(b)
        elif fill >= near_threshold_floor or time_overflow < 4.0:
            near_threshold.append(b)
        else:
            low_urgency.append(b)
    
    return critical, near_threshold, low_urgency


def _effective_threshold(bin_data: Dict) -> float:
    return float(bin_data.get('dynamic_threshold') or bin_data.get('threshold', 80))


def _bin_volume(bin_data: Dict) -> float:
    capacity = float(bin_data.get('capacity', 500))
    fill_pct = float(bin_data.get('fillLevel', 0))
    capacity = max(0.0, capacity)
    fill_pct = max(0.0, min(100.0, fill_pct))
    return (fill_pct / 100.0) * capacity


def _should_dispatch_unified(critical_bins: list, near_threshold_bins: list, 
                            trucks: list) -> bool:
    """
    Unified dispatch decision: Should we dispatch now?
    Rules: Always dispatch if critical bins. Dispatch if near-threshold accumulates.
    """
    if not trucks:
        return False
    
    # Always dispatch critical bins
    if critical_bins:
        return True
    
    # Dispatch if we have 40% of avg truck capacity in near-threshold bins
    if not near_threshold_bins:
        return False

    total_waste_volume = sum(_bin_volume(b) for b in near_threshold_bins)
    avg_capacity = sum(max(t.get('capacity', 1500), 1) for t in trucks) / len(trucks)

    if avg_capacity <= 0:
        return False

    return (total_waste_volume / avg_capacity) >= 0.35


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
    
    # Check for bins that exceeded their effective threshold
    critical_bins = [
        b for b in urgent_bins if b.get('fillLevel', 0) >= _effective_threshold(b)
    ]
    
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


def _ensure_distance_matrix(app, bins: list) -> None:
    """Ensure the shared distance matrix is up-to-date before computing routes."""
    service = getattr(app, 'distance_matrix_service', None)
    if not service:
        return
    depots = app.system_repository.get_depots()
    summary = service.build_matrices(bins, depots)
    status = summary.get('status', 'unknown')
    if status == 'rebuilt':
        print(f"🧮 Distance matrix rebuilt in {summary.get('build_seconds', 0):.2f}s")
    else:
        print("✅ Distance matrix cache reused")



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


def _should_use_proximity_routes(current_routes: list, proximity_routes: list, trucks: list) -> bool:
    if not proximity_routes:
        return False
    if not current_routes:
        return True

    current_trucks = {
        route['truck_id']
        for route in current_routes
        if route.get('bin_ids')
    }
    proximity_trucks = {route['truck_id'] for route in proximity_routes}

    if not current_trucks and proximity_trucks:
        return True

    if len(trucks) > 1 and len(proximity_trucks) > len(current_trucks):
        return True

    covered_by_current = {
        bin_id
        for route in current_routes
        for bin_id in route.get('bin_ids', [])
    }
    covered_by_proximity = {
        bin_id
        for route in proximity_routes
        for bin_id in route.get('bin_ids', [])
    }

    return bool(covered_by_proximity - covered_by_current)


def _select_active_dispatch_bins(
    bins: list,
    critical_bins: list,
    depot: Dict
) -> list:
    if not bins:
        return []

    if len(critical_bins) == 1:
        return _cluster_bins_around_primary(critical_bins[0], bins, depot)

    return bins


def _cluster_bins_around_primary(primary_bin: Dict, bins: list, depot: Dict) -> list:
    if not primary_bin:
        return bins

    primary_id = primary_bin.get('id')
    cluster = []
    seen_ids = set()

    for bin_data in bins:
        bin_id = bin_data.get('id')
        if bin_id and bin_id == primary_id:
            cluster.append(bin_data)
            seen_ids.add(bin_id)
            break

    others = [b for b in bins if b.get('id') not in seen_ids]

    primary_depot_distance = _distance_from_bin_to_depot(primary_bin, depot)
    if not primary_depot_distance or primary_depot_distance == float('inf'):
        primary_depot_distance = SINGLE_TRIGGER_RADIUS_MAX

    radius = max(
        SINGLE_TRIGGER_RADIUS_MIN,
        min(primary_depot_distance * 0.6, SINGLE_TRIGGER_RADIUS_MAX)
    )

    def distance_to_primary(candidate: Dict) -> float:
        return _distance_between_coords(
            primary_bin.get('lat'), primary_bin.get('lng'),
            candidate.get('lat'), candidate.get('lng')
        )

    ordered_candidates = sorted(
        others,
        key=lambda candidate: (
            distance_to_primary(candidate),
            -float(candidate.get('fillRate', 0.0))
        )
    )

    for candidate in ordered_candidates:
        if len(cluster) >= SINGLE_TRIGGER_MAX_BINS:
            break

        dist_to_primary = distance_to_primary(candidate)
        depot_distance = _distance_from_bin_to_depot(candidate, depot)

        same_direction = dist_to_primary <= depot_distance * 0.8
        within_radius = dist_to_primary <= radius
        urgent_candidate = candidate.get('fillLevel', 0) >= _effective_threshold(candidate) - 5

        if same_direction or within_radius or urgent_candidate:
            cluster.append(candidate)

    return cluster if cluster else bins


def _select_trucks_for_active_dispatch(
    trucks: list,
    critical_bins: list,
    depot: Dict
) -> list:
    if not trucks:
        return []

    if len(critical_bins) == 1:
        primary_bin = critical_bins[0]
        sorted_trucks = sorted(
            [t for t in trucks if t.get('id')],
            key=lambda truck: _distance_truck_to_bin(truck, primary_bin, depot)
        )
        if sorted_trucks:
            return sorted_trucks[:1]

    return trucks


def _build_proximity_routes(
    bins: list,
    trucks: list,
    depot: Dict,
    distance_service: Optional[Any] = None
) -> list:
    if not bins or not trucks:
        return []

    assignments = _assign_bins_to_trucks_by_distance(bins, trucks, depot)
    routes = []

    for truck in trucks:
        truck_id = truck.get('id')
        if not truck_id:
            continue
        assigned_bins = assignments.get(truck_id, [])
        if not assigned_bins:
            continue

        ordered_bins, total_distance = _order_bins_for_truck(
            truck, assigned_bins, depot, distance_service
        )
        if not ordered_bins:
            continue

        speed_kmh = max(float(truck.get('speed', 40) or 40), 1.0)
        duration_seconds = int(((total_distance / 1000.0) / speed_kmh) * 3600)

        routes.append({
            'truck_id': truck_id,
            'bin_ids': [b['id'] for b in ordered_bins if b.get('id')],
            'distance': int(total_distance),
            'duration': max(duration_seconds, 0)
        })

    return [route for route in routes if route['bin_ids']]


def _assign_bins_to_trucks_by_distance(bins: list, trucks: list, depot: Dict) -> Dict[str, list]:
    assignments = {truck['id']: [] for truck in trucks if truck.get('id')}
    if not assignments:
        return {}

    truck_loads = {truck_id: 0.0 for truck_id in assignments.keys()}
    bin_queue = sorted(
        [b for b in bins if b.get('id')],
        key=lambda b: (
            -float(b.get('urgency_score', b.get('fillLevel', 0))),
            b['id']
        )
    )

    for bin_data in bin_queue:
        best_truck = None
        best_score = None
        for truck in trucks:
            truck_id = truck.get('id')
            if truck_id not in assignments:
                continue
            dist = _distance_truck_to_bin(truck, bin_data, depot)
            score = (dist, truck_loads[truck_id])
            if best_score is None or score < best_score:
                best_score = score
                best_truck = truck
        if best_truck is None:
            continue
        truck_id = best_truck['id']
        assignments[truck_id].append(bin_data)
        truck_loads[truck_id] += _bin_volume(bin_data)

    return assignments


def _order_bins_for_truck(
    truck: Dict,
    assigned_bins: list,
    depot: Dict,
    distance_service: Optional[Any] = None
) -> tuple[list, float]:
    remaining = list(assigned_bins)
    ordered: list = []
    total_distance = 0.0
    current_lat, current_lng = _truck_coordinates(truck, depot)
    current_bin: Optional[Dict] = None

    while remaining:
        next_bin = min(
            remaining,
            key=lambda b: _distance_to_bin(current_bin, current_lat, current_lng, b, distance_service)
        )
        next_distance = _distance_to_bin(
            current_bin, current_lat, current_lng, next_bin, distance_service
        )
        total_distance += next_distance
        ordered.append(next_bin)
        current_bin = next_bin
        current_lat = next_bin.get('lat')
        current_lng = next_bin.get('lng')
        remaining.remove(next_bin)

    if ordered:
        total_distance += _distance_from_bin_to_depot(ordered[-1], depot, distance_service)

    return ordered, total_distance


def _distance_to_bin(
    current_bin: Optional[Dict],
    current_lat: Optional[float],
    current_lng: Optional[float],
    target_bin: Dict,
    distance_service: Optional[Any] = None
) -> float:
    if current_bin and distance_service:
        bin_id = current_bin.get('id')
        target_id = target_bin.get('id')
        if bin_id and target_id:
            cached = distance_service.get_bin_to_bin_distance(bin_id, target_id)
            if cached is not None:
                return cached

    if current_bin:
        return _distance_between_coords(
            current_bin.get('lat'), current_bin.get('lng'),
            target_bin.get('lat'), target_bin.get('lng')
        )

    return _distance_between_coords(
        current_lat, current_lng, target_bin.get('lat'), target_bin.get('lng')
    )


def _distance_from_bin_to_depot(
    bin_data: Dict,
    depot: Dict,
    distance_service: Optional[Any] = None
) -> float:
    depot_id = depot.get('id')
    bin_id = bin_data.get('id')
    if distance_service and depot_id and bin_id:
        cached = distance_service.get_bin_to_depot_distance(bin_id, depot_id)
        if cached is not None:
            return cached
    return _distance_between_coords(
        bin_data.get('lat'), bin_data.get('lng'), depot.get('lat'), depot.get('lng')
    )


def _distance_truck_to_bin(truck: Dict, bin_data: Dict, depot: Dict) -> float:
    lat, lng = _truck_coordinates(truck, depot)
    return _distance_between_coords(lat, lng, bin_data.get('lat'), bin_data.get('lng'))


def _truck_coordinates(truck: Dict, depot: Dict) -> tuple[Optional[float], Optional[float]]:
    lat = truck.get('lat')
    lng = truck.get('lng')
    if lat is None or lng is None:
        lat = depot.get('lat')
        lng = depot.get('lng')
    return lat, lng


def _distance_between_coords(
    lat1: Optional[float],
    lng1: Optional[float],
    lat2: Optional[float],
    lng2: Optional[float]
) -> float:
    if None in (lat1, lng1, lat2, lng2):
        return float('inf')
    return calculate_haversine_distance(float(lat1), float(lng1), float(lat2), float(lng2))


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
