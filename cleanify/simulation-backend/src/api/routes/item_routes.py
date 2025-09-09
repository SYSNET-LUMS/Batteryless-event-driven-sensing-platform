from flask import Blueprint, jsonify, request, current_app
from config.constants import ITEM_CONFIGS
from services import WasteCollectionAgent

bp = Blueprint('items', __name__, url_prefix='/api')

@bp.route('/<item_type>', methods=['POST'])
def add_item(item_type):
    """Generic add function for bin/truck/depot"""
    try:
        if item_type not in ITEM_CONFIGS:
            return jsonify({"status": "error", "message": f"Invalid item type: {item_type}"}), 400
        
        data = request.json
        config = ITEM_CONFIGS[item_type]
        
        # Validate required fields
        for field in config['required_fields']:
            if field not in data:
                return jsonify({"status": "error", "message": f"Missing field: {field}"}), 400
        
        # Apply default values
        for key, value in config['default_values'].items():
            if key not in data:
                data[key] = value
        
        # Add item based on type
        repo = current_app.system_repository
        
        if item_type == 'bin':
            item = repo.add_bin(data)
        elif item_type == 'truck':
            item = repo.add_truck(data)
        elif item_type == 'depot':
            item = repo.add_depot(data)
            # Initialize agent on first depot
            if current_app.agent is None:
                current_app.agent = WasteCollectionAgent()
                current_app.agent.bins_data = repo.get_bins()
                print(f"Initialized agent with depot {item['id']}")
        
        return jsonify({"status": "success", item_type: item})
        
    except Exception as e:
        print(f"⚠ Error adding {item_type}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/<item_type>', methods=['PUT'])
def update_item(item_type):
    """Generic update function"""
    try:
        if item_type not in ITEM_CONFIGS:
            return jsonify({"status": "error", "message": f"Invalid item type: {item_type}"}), 400
        
        data = request.json
        item_id = data.get('id')
        
        if not item_id:
            return jsonify({"status": "error", "message": "Missing item ID"}), 400
        
        repo = current_app.system_repository
        
        if item_type == 'bin':
            item = repo.update_bin(item_id, data)
        elif item_type == 'truck':
            item = repo.update_truck(item_id, data)
        elif item_type == 'depot':
            item = repo.update_depot(item_id, data)
        
        if item:
            return jsonify({"status": "success", item_type: item})
        else:
            return jsonify({"status": "error", "message": f"{item_type.title()} not found"}), 404
        
    except Exception as e:
        print(f"⚠ Error updating {item_type}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/<item_type>', methods=['DELETE'])
def delete_item(item_type):
    """Generic delete function"""
    try:
        if item_type not in ITEM_CONFIGS:
            return jsonify({"status": "error", "message": f"Invalid item type: {item_type}"}), 400
        
        data = request.json
        item_id = data.get('id')
        
        if not item_id:
            return jsonify({"status": "error", "message": "Missing item ID"}), 400
        
        repo = current_app.system_repository
        
        if item_type == 'bin':
            deleted_item = repo.delete_bin(item_id)
        elif item_type == 'truck':
            deleted_item = repo.delete_truck(item_id)
        elif item_type == 'depot':
            deleted_item = repo.delete_depot(item_id)
        
        if deleted_item:
            return jsonify({
                "status": "success",
                "message": f"{item_type.title()} {item_id} deleted",
                f"deleted_{item_type}": deleted_item
            })
        else:
            return jsonify({"status": "error", "message": f"{item_type.title()} not found"}), 404
        
    except Exception as e:
        print(f"⚠ Error deleting {item_type}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500