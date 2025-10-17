"""
Pytest configuration for Cleanify test suite.
Loads environment variables before running tests.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from repository root
REPO_ROOT = Path(__file__).parent.parent
ENV_PATH = REPO_ROOT / '.env'
load_dotenv(dotenv_path=ENV_PATH)
print(f"🔧 Test suite loaded environment from: {ENV_PATH}")

# Add src to path for imports
SRC_PATH = REPO_ROOT / 'cleanify' / 'simulation-backend' / 'src'
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
    print(f"📁 Added to Python path: {SRC_PATH}")
