
from flask import Blueprint, request, jsonify, current_app
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
        repo = current_app.system_repository
        data = request.json
        # Clear only bins, trucks, depots
        repo._bins.clear()
        repo._trucks.clear()
        repo._depots.clear()
        repo._id_counters['bin'] = 0
        repo._id_counters['truck'] = 0
        repo._id_counters['depot'] = 0
        # Add new items with validation/defaults
        for bin_data in data.get('bins', []):
            validated_bin = validate_and_apply_defaults('bin', bin_data)
            repo.add_bin(validated_bin)
        for truck_data in data.get('trucks', []):
            validated_truck = validate_and_apply_defaults('truck', truck_data)
            repo.add_truck(validated_truck)
        for depot_data in data.get('depots', []):
            validated_depot = validate_and_apply_defaults('depot', depot_data)
            repo.add_depot(validated_depot)
        # Ensure agent is initialized if depots exist
        if repo.get_depots() and getattr(current_app, 'agent', None) is None:
            from services import WasteCollectionAgent
            current_app.agent = WasteCollectionAgent()
            current_app.agent.bins_data = repo.get_bins()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
