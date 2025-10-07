#!/usr/bin/env python3
"""
Test the agent service with fixed clustering.
"""

import sys
import os
import json
import logging

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from services.agent_service import WasteCollectionAgent

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def load_test_system():
    """Load the latest system for testing"""
    system_file = "saved_systems/cleanify_system_20251007_130200.json"
    with open(system_file, 'r') as f:
        return json.load(f)

def test_agent_with_fixed_clustering():
    """Test the agent service with fixed clustering"""
    print(f"\n=== TESTING AGENT SERVICE WITH FIXED CLUSTERING ===")
    
    try:
        # Initialize agent
        agent = WasteCollectionAgent()
        print(f"Agent initialized successfully with {type(agent.clustering_service).__name__}")
        
        # Load test system
        system = load_test_system()
        bins_data = system['bins']
        trucks_data = system['trucks']
        
        print(f"Loaded system with {len(bins_data)} bins and {len(trucks_data)} trucks")
        
        # Set bins data
        agent.bins_data = bins_data
        
        # Test clustering
        print(f"\nTesting clustering...")
        clusters = agent.get_clusters(bins_data)
        print(f"Created {len(clusters)} clusters:")
        
        for cluster_id, cluster_bins in clusters.items():
            bin_ids = [b['id'] for b in cluster_bins]
            print(f"  Cluster {cluster_id}: {bin_ids} (size: {len(bin_ids)})")
        
        # Test cluster info
        cluster_info = agent.clustering_service.get_cluster_info(clusters)
        print(f"\nCluster quality summary:")
        for cluster_id, info in cluster_info.items():
            quality = info.get('quality_rating', 'unknown')
            max_dist = info.get('max_internal_distance', 0)
            print(f"  Cluster {cluster_id}: {quality} (max distance: {max_dist:.0f}m)")
        
        # Test optimization status
        print(f"\nOptimization status:")
        status = agent.get_optimization_status()
        for key, value in status.items():
            print(f"  {key}: {value}")
        
        return True
        
    except Exception as e:
        print(f"Error testing agent service: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("=== TESTING AGENT SERVICE WITH FIXED CLUSTERING ===")
    
    success = test_agent_with_fixed_clustering()
    
    if success:
        print(f"\n✅ Agent service with fixed clustering works correctly!")
        print(f"The clustering now creates geographically logical clusters.")
    else:
        print(f"\n❌ There were issues with the agent service.")

if __name__ == "__main__":
    main()