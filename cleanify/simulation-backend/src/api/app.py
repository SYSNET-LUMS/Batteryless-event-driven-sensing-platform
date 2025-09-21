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
    app.system_repository = SystemRepository()
    app.agent = None
    app.clustering_service = ClusteringService(config)
    app.routing_service = RoutingService(config)
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
    
    return app