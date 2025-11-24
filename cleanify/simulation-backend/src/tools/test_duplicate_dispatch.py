#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from repository root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
REPO_ROOT = Path(SRC_DIR).parent.parent.parent
ENV_PATH = REPO_ROOT / '.env'
load_dotenv(dotenv_path=ENV_PATH)
print(f"🔧 Test script loaded environment from: {ENV_PATH}")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.agent_service import WasteCollectionAgent


def main(system_path: str):
    with open(system_path, 'r') as f:
        data = json.load(f)
    bins = data['bins']
    trucks = data['trucks']
    depots = data['depots']

    agent = WasteCollectionAgent()
    agent.bins_data = bins
    agent.depot_data = depots
    agent.distance_cache.warm_cache(bins, depots)

    # First: process DT for BIN_2 to create a dispatch plan
    bin2 = next(b for b in bins if b['id'] == 'BIN_2')
    result1 = agent.handle_bin_reached_dt(bin2, bins, trucks, 0.0)
    print("First DT (BIN_2) decision:", result1)

    # Second: process DT for BIN_3 (same neighborhood)
    bin3 = next(b for b in bins if b['id'] == 'BIN_3')
    result2 = agent.handle_bin_reached_dt(bin3, bins, trucks, 60.0)
    print("Second DT (BIN_3) decision:", result2)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python -m tools.test_duplicate_dispatch <path-to-system.json>")
        sys.exit(1)
    main(sys.argv[1])
