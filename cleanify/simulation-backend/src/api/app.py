"""
Minimalist Flask Application
Simple service initialization with traffic-aware dispatch
"""

from flask import Flask
from flask_cors import CORS
from config.settings import Config
from repositories.system_repository import SystemRepository, get_system_repository
from services.traffic_service import TrafficService
from services.routing_service import RoutingService
from services.file_service import FileService
from services.schedule_service import ScheduleService
from services.external.osrm_service import OSRMService
from services.external.vroom_service import VROOMService
from services.simulation.simulation_service import SimulationService
from .routes import (
    system_routes,
    item_routes,
    simulation_routes,
    dispatch_routes,
    file_routes,
    config_routes,
    schedule_routes,
    batch_sync_routes
)


def create_app(config: Config = None) -> Flask:
    """Create minimalist Flask app"""
    app = Flask(__name__)
    
    if config is None:
        config = Config()
    
    # CORS
    CORS(app, origins="*", methods=['GET', 'POST', 'PUT', 'DELETE'], 
         allow_headers=['Content-Type'])
    
    # Initialize core services only
    app.system_repository = get_system_repository()
    app.osrm_service = OSRMService(config)
    app.traffic_service = TrafficService(config)
    app.vroom_service = VROOMService(config)
    app.routing_service = RoutingService(config, osrm_service=app.osrm_service)
    app.simulation_service = SimulationService(app.osrm_service)
    app.file_service = FileService(config.SAVES_DIR)
    app.schedule_service = ScheduleService()
    app.config_obj = config
    
    # Register blueprints
    app.register_blueprint(system_routes.bp)
    app.register_blueprint(item_routes.bp)
    app.register_blueprint(simulation_routes.bp)
    app.register_blueprint(dispatch_routes.bp)  # NEW
    app.register_blueprint(file_routes.bp)
    app.register_blueprint(config_routes.bp)
    app.register_blueprint(schedule_routes.bp)
    app.register_blueprint(batch_sync_routes.bp)
    
    print("✅ Minimalist Cleanify backend initialized")
    print(f"   - Traffic heavy hours: {config.TRAFFIC_HEAVY_HOURS}")
    print(f"   - VROOM URL: {config.VROOM_URL}")
    print(f"   - OSRM URL: {config.OSRM_URL}")
    
    return app