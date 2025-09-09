import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from api.app import create_app
from config.settings import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Main entry point for the application"""
    config = Config()
    app = create_app(config)
    
    logger.info(f"Starting Cleanify Backend on {config.HOST}:{config.PORT}")
    app.run(
        debug=config.DEBUG,
        host=config.HOST,
        port=config.PORT
    )

if __name__ == '__main__':
    main()