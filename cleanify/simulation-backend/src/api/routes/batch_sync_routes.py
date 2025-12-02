from flask import Blueprint, request, jsonify, current_app
from typing import Any, cast
from config.constants import ITEM_CONFIGS

bp = Blueprint('batch_sync', __name__, url_prefix='/api')

def validate_and_apply_defaults(item_type, item):
    config = ITEM_CONFIGS[item_type]
    # Validate required fields
    for field in config['required_fields']:
        if field not in item:
            raise ValueError(f"Missing required field '{field}' for {item_type}")
    # Apply default values
    for key, value in config['default_values'].items():
        if key not in item:
            item[key] = value
    return item

@bp.route('/batch_sync', methods=['POST'])
def batch_sync():
    """Batch sync bins, trucks, and depots in one request. Schedules are not touched."""
    try:
        app = cast(Any, current_app)
        repo = app.system_repository
        data = request.json
        if not isinstance(data, dict):
            return jsonify({'status': 'error', 'message': 'Invalid or missing JSON body'}), 400
        # Clear only bins, trucks, depots
        repo._bins.clear()
        repo._trucks.clear()
        repo._depots.clear()
        repo._id_counters['bin'] = 0
        repo._id_counters['truck'] = 0
        repo._id_counters['depot'] = 0
        # Add new items with validation/defaults
        bins = [validate_and_apply_defaults('bin', bin_data) for bin_data in data.get('bins', [])]
        trucks = [validate_and_apply_defaults('truck', truck_data) for truck_data in data.get('trucks', [])]
        depots = [validate_and_apply_defaults('depot', depot_data) for depot_data in data.get('depots', [])]

        # Assign IDs in a single pass
        repo._bins = []
        for i, bin_data in enumerate(bins, 1):
            bin_data['id'] = f"BIN_{i}"
            repo._bins.append(bin_data)
        repo._id_counters['bin'] = len(bins)

        repo._trucks = []
        for i, truck_data in enumerate(trucks, 1):
            truck_data['id'] = f"TRUCK_{i}"
            repo._trucks.append(truck_data)
        repo._id_counters['truck'] = len(trucks)

        repo._depots = []
        for i, depot_data in enumerate(depots, 1):
            depot_data['id'] = f"DEPOT_{i}"
            repo._depots.append(depot_data)
        repo._id_counters['depot'] = len(depots)
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
