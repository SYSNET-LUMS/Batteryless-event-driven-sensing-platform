ITEM_CONFIGS = {
    'bin': {
        'id_prefix': 'BIN_',
        'required_fields': ['lat', 'lng'],
        'default_values': {
            'fillLevel': 20,
            'capacity': 500,
            'fillRate': 3.5,
            'threshold': 80
        }
    },
    'truck': {
        'id_prefix': 'TRUCK_',
        'required_fields': ['lat', 'lng'],
        'default_values': {
            'capacity': 1000,
            'currentLoad': 0,
            'status': 'idle',
            'speed': 50
        }
    },
    'depot': {
        'id_prefix': 'DEPOT_',
        'required_fields': ['lat', 'lng'],
        'default_values': {
            'name': 'Default Depot'
        }
    }
}

# Traffic profiles
BIN_TRAFFIC_PROFILES = {
    "BIN_1": {
        "road_type": "highway",
        "pattern": {
            7: 2.0, 8: 6.0, 9: 2.0,
            10: 2.0, 11: 1.5, 12: 1.5,
            17: 5.0, 18: 6.0, 19: 4.0,
            20: 2.0, 21: 1.5, 22: 1.2 
        }
    },
    "BIN_2": {  
        "road_type": "residential", 
        "pattern": {
            7: 1.5, 8: 2.0, 9: 1.8,   
            10: 1.2, 11: 1.0, 12: 1.0, 
            17: 1.8, 18: 2.0, 19: 1.5, 
            20: 1.0, 21: 1.0, 22: 1.0  
        }
    }
}