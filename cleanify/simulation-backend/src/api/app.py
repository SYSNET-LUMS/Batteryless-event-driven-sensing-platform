from flask import Flask
from flask_cors import CORS
from config.settings import Config
from repositories.system_repository import SystemRepository
from services import (
    WasteCollectionAgent,
    ClusteringService,
    RoutingService,
    FileService,
    ScheduleService
)
from services.external.osrm_service import OSRMService
from .routes import (
    system_routes,
    item_routes,
    simulation_routes,
    ai_routes,
    file_routes,
    config_routes,
    schedule_routes
)

def create_app(config: Config = None) -> Flask:
    """Create and configure Flask application"""
    app = Flask(__name__)
    
    if config is None:
        config = Config()
    
    # Configure CORS
    CORS(app, origins="*", methods=['GET', 'POST', 'PUT', 'DELETE'], 
         allow_headers=['Content-Type'])
    
    # Initialize services
    from repositories.system_repository import get_system_repository
    app.system_repository = get_system_repository()
    app.agent = None
    # Create shared OSRM service instance to enable cross-service caching
    app.osrm_service = OSRMService(config)
    app.clustering_service = ClusteringService(config, osrm_service=app.osrm_service)
    app.routing_service = RoutingService(config, osrm_service=app.osrm_service)
    app.file_service = FileService(config.SAVES_DIR)
    app.schedule_service = ScheduleService()
    app.config_obj = config
    
    # Register blueprints
    app.register_blueprint(system_routes.bp)
    app.register_blueprint(item_routes.bp)
    app.register_blueprint(simulation_routes.bp)
    app.register_blueprint(ai_routes.bp)
    app.register_blueprint(file_routes.bp)
    app.register_blueprint(config_routes.bp)
    app.register_blueprint(schedule_routes.bp)
    from .routes import batch_sync_routes
    app.register_blueprint(batch_sync_routes.bp)
    
    return app