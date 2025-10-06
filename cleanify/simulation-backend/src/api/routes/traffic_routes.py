from flask import Blueprint, jsonify, request, current_app
from services.traffic.dispatch_service import DispatchService
from utils.distance import calculate_distance_km

bp = Blueprint('traffic', __name__, url_prefix='/api/traffic')

def _pick_best_truck_for_bin(bin_data, trucks):
    """Select nearest idle truck; fallback to any idle truck; return None if none."""
    idle = [t for t in trucks if t.get('status') == 'idle']
    if not idle:
        return None
    # Distance-based selection
    scored = []
    for t in idle:
        try:
            d = calculate_distance_km(bin_data['lat'], bin_data['lng'], t['lat'], t['lng'])
        except Exception:
            d = 9999
        scored.append((d, t))
    scored.sort(key=lambda x: x[0])
    return scored[0][1]

def _evaluate_bins(simulation_time_seconds: float):
    repo = current_app.system_repository  # type: ignore[attr-defined]
    bins = repo.get_bins() or []
    trucks = repo.get_trucks() or []
    if not bins or not trucks:
        return [], {
            'total_bins': len(bins),
            'dispatch_now': 0,
            'wait': 0,
            'strategy_breakdown': {}
        }

    dispatch_service = DispatchService(current_app.osrm_service)  # type: ignore[attr-defined]
    decisions = []
    strategy_counts = {}
    dispatch_now = 0
    wait_ct = 0

    for b in bins:
        truck = _pick_best_truck_for_bin(b, trucks)
        if not truck:
            continue
        decision = dispatch_service.should_dispatch_now(b, truck, simulation_time_seconds)
        # Enrich with bin + truck context
        enriched = {
            'bin_id': b.get('id'),
            'fillLevel': b.get('fillLevel'),
            'threshold': b.get('dynamic_threshold', b.get('threshold')),
            'truck_id': truck.get('id'),
            'dispatch': decision.get('dispatch'),
            'delay_min': decision.get('delay_min'),
            'reason': decision.get('reason'),
            'strategy': decision.get('strategy'),
            'decision_source': decision.get('decision_source'),
            'fuel_savings_min': decision.get('fuel_savings_min'),
            'future_traffic_level': decision.get('future_traffic_level'),
        }
        decisions.append(enriched)
        if enriched['dispatch'] == 'now':
            dispatch_now += 1
        else:
            wait_ct += 1
        strat = enriched.get('strategy') or 'none'
        strategy_counts[strat] = strategy_counts.get(strat, 0) + 1

    summary = {
        'total_bins': len(bins),
        'evaluated_bins': len(decisions),
        'dispatch_now': dispatch_now,
        'wait': wait_ct,
        'strategy_breakdown': strategy_counts
    }
    return decisions, summary

@bp.route('/dispatch_decisions', methods=['GET'])
def get_dispatch_decisions():
    try:
        simulation_time = float(request.args.get('simulation_time', 0))
        decisions, summary = _evaluate_bins(simulation_time)
        return jsonify({
            'status': 'success',
            'simulation_time': simulation_time,
            'decisions': decisions,
            'summary': summary
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@bp.route('/strategy_summary', methods=['GET'])
def get_strategy_summary():
    try:
        simulation_time = float(request.args.get('simulation_time', 0))
        _, summary = _evaluate_bins(simulation_time)
        return jsonify({
            'status': 'success',
            'simulation_time': simulation_time,
            'summary': summary
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
