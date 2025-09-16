from flask import Blueprint, jsonify, current_app
from config.settings import Config
from config.constants import BIN_TRAFFIC_PROFILES

bp = Blueprint('config', __name__, url_prefix='/api')

@bp.route('/config', methods=['GET'])
def get_config():
    """Get configuration settings for frontend synchronization"""
    try:
        config = Config()
        
        return jsonify({
            "status": "success",
            "config": {
                "simulation_start_hour": config.SIMULATION_START_HOUR,
                "default_bin_capacity": config.DEFAULT_BIN_CAPACITY,
                "default_truck_capacity": config.DEFAULT_TRUCK_CAPACITY,
                "default_fill_rate": config.DEFAULT_FILL_RATE,
                "cluster_eps_meters": config.CLUSTER_EPS_METERS,
                "cluster_min_samples": config.CLUSTER_MIN_SAMPLES
            }
        })
        
    except Exception as e:
        print(f"⚠️ Config fetch error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/config/simulation_start_hour', methods=['GET'])
def get_simulation_start_hour():
    """Get just the simulation start hour for time synchronization"""
    try:
        config = Config()
        
        return jsonify({
            "status": "success",
            "simulation_start_hour": config.SIMULATION_START_HOUR
        })
        
    except Exception as e:
        print(f"⚠️ Simulation start hour fetch error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/config/traffic_info', methods=['GET'])
def get_traffic_info():
    """Get current traffic information based on simulation time"""
    try:
        from flask import request
        config = Config()
        
        # Get simulation time from query parameter (in minutes)
        simulation_time = int(request.args.get('simulation_time', 0))
        
        # Calculate current time
        start_hour = config.SIMULATION_START_HOUR
        current_time_min = (start_hour * 60) + (simulation_time // 60)
        current_hour = (current_time_min // 60) % 24
        
        # Calculate traffic density using BIN_TRAFFIC_PROFILES
        density = 1.0  # Default density
        
        # Use BIN_1 pattern as default (highway traffic pattern)
        if "BIN_1" in BIN_TRAFFIC_PROFILES:
            traffic_pattern = BIN_TRAFFIC_PROFILES["BIN_1"]["pattern"]
            density = traffic_pattern.get(current_hour, 1.0)
        
        # Determine traffic level
        if density > 5:
            traffic_level = 'Heavy'
        elif density > 2:
            traffic_level = 'Moderate'
        else:
            traffic_level = 'Light'
        
        return jsonify({
            "status": "success",
            "traffic_info": {
                "current_density": density,
                "current_hour": current_hour,
                "time_of_day": f"{current_hour:02d}:{(current_time_min % 60):02d}",
                "traffic_level": traffic_level
            }
        })
        
    except Exception as e:
        print(f"⚠️ Traffic info fetch error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500