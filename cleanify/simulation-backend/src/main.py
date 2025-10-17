import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in repository root
# Path: Cleanify/.env (two levels up from src/)
env_path = Path(__file__).parent.parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
print(f"🔧 Loaded environment from: {env_path}")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from api.app import create_app
from config.settings import Config

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

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