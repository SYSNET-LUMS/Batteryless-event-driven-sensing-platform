#!/usr/bin/env python3
"""
Test the simple dynamic clustering service.
"""

import sys
import os
import json
import logging

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from services.simple_dynamic_clustering_service import SimpleDynamicClusteringService
from utils.distance import calculate_haversine_distance

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def load_systems():
    """Load both test systems"""
    systems = {}
    
    # Small scale system (problematic)
    with open("saved_systems/cleanify_system_20250819_002311.json", 'r') as f:
        systems['small'] = json.load(f)
    
    # Large scale system 
    with open("saved_systems/cleanify_system_20251007_130200.json", 'r') as f:
        systems['large'] = json.load(f)
    
    return systems

def test_simple_dynamic_clustering(system_name, system_data):
    """Test the simple dynamic clustering service"""
    print(f"\n=== TESTING SIMPLE DYNAMIC CLUSTERING: {system_name.upper()} SYSTEM ===")
    
    bins_data = system_data['bins']
    depot_data = system_data.get('depots', [{}])[0] if system_data.get('depots') else None
    
    clustering_service = SimpleDynamicClusteringService()
    
    try:
        # Get clustering info first
        info = clustering_service.get_clustering_info(bins_data, depot_data)
        print(f"\nClustering Approach Info:")
        print(f"  Approach: {info['approach']}")
        print(f"  Dynamic threshold: {info['dynamic_threshold_m']:.0f}m")
        print(f"  Depot distance percentage: {info['depot_distance_percentage']:.0f}%")
        print(f"  Threshold bounds: {info['min_threshold_m']}-{info['max_threshold_m']}m")
        print(f"  Has depot data: {info['has_depot_data']}")
        
        if info['depot_distances']['avg_m']:
            depot_dist = info['depot_distances']
            print(f"  Depot distances: min={depot_dist['min_m']:.0f}m, "
                  f"avg={depot_dist['avg_m']:.0f}m, max={depot_dist['max_m']:.0f}m")
        
        # Create clusters
        clusters = clustering_service.create_simple_dynamic_clusters(bins_data, depot_data)
        print(f"\nClustering Results:")
        print(f"  Created {len(clusters)} clusters:")
        
        for cluster_id, cluster_bins in clusters.items():
            bin_ids = [b['id'] for b in cluster_bins]
            print(f"    Cluster {cluster_id}: {bin_ids} (size: {len(bin_ids)})")
            
            # Calculate cluster quality
            if len(cluster_bins) > 1:
                max_dist = 0
                distances = []
                for i in range(len(cluster_bins)):
                    for j in range(i + 1, len(cluster_bins)):
                        dist = calculate_haversine_distance(
                            cluster_bins[i]['lat'], cluster_bins[i]['lng'],
                            cluster_bins[j]['lat'], cluster_bins[j]['lng']
                        )
                        distances.append(dist)
                        max_dist = max(max_dist, dist)
                avg_dist = sum(distances) / len(distances)
                print(f"      Max internal distance: {max_dist:.1f}m, Avg: {avg_dist:.1f}m")
        
        # Get cluster info
        cluster_info = clustering_service.get_cluster_info(clusters)
        print(f"\nCluster Quality:")
        excellent_count = 0
        for cluster_id, info in cluster_info.items():
            quality = info.get('quality_metrics', {})
            rating = quality.get('quality_rating', 'unknown')
            compactness = quality.get('compactness_score', 0)
            efficiency = quality.get('collection_efficiency', 0)
            
            if rating == 'excellent':
                excellent_count += 1
                
            print(f"    Cluster {cluster_id}: {rating} (compactness: {compactness:.2f}, efficiency: {efficiency:.2f})")
        
        quality_percentage = (excellent_count / len(clusters) * 100) if clusters else 0
        print(f"  Overall: {excellent_count}/{len(clusters)} clusters rated excellent ({quality_percentage:.0f}%)")
        
        return clusters, info
        
    except Exception as e:
        print(f"Error with SimpleDynamicClusteringService: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def test_with_different_depot_percentages(system_name, system_data):
    """Test different depot percentage values"""
    print(f"\n=== TESTING DIFFERENT DEPOT PERCENTAGES: {system_name.upper()} ===")
    
    bins_data = system_data['bins']
    depot_data = system_data.get('depots', [{}])[0] if system_data.get('depots') else None
    
    if not depot_data:
        print("No depot data available for percentage testing")
        return
    
    percentages = [0.10, 0.15, 0.20, 0.25, 0.30]  # 10% to 30%
    
    for percentage in percentages:
        print(f"\n--- Testing {percentage*100:.0f}% depot distance ---")
        
        clustering_service = SimpleDynamicClusteringService()
        clustering_service.depot_distance_percentage = percentage
        
        try:
            clusters = clustering_service.create_simple_dynamic_clusters(bins_data, depot_data)
            info = clustering_service.get_clustering_info(bins_data, depot_data)
            
            print(f"  Threshold: {info['dynamic_threshold_m']:.0f}m")
            print(f"  Clusters: {len(clusters)}")
            
            cluster_sizes = [len(cluster) for cluster in clusters.values()]
            print(f"  Cluster sizes: {cluster_sizes}")
            
        except Exception as e:
            print(f"  Error: {e}")

def compare_with_expected(system_name, clusters):
    """Compare with expected geographical clustering"""
    print(f"\n=== COMPARISON WITH EXPECTED: {system_name.upper()} ===")
    
    if system_name == 'small':
        expected = [
            ["BIN_1", "BIN_2", "BIN_6"],  # Northern group
            ["BIN_3", "BIN_4", "BIN_7"],  # Eastern group  
            ["BIN_5"]  # Isolated
        ]
        print("Expected 3 clusters:")
        print("  [BIN_1, BIN_2, BIN_6] - Northern group")
        print("  [BIN_3, BIN_4, BIN_7] - Eastern group")
        print("  [BIN_5] - Isolated")
    else:
        expected = [
            ["BIN_1", "BIN_2", "BIN_3", "BIN_4"],  # Central-North
            ["BIN_5", "BIN_6", "BIN_7"],  # West
            ["BIN_8", "BIN_9", "BIN_10"]  # South
        ]
        print("Expected 3 clusters:")
        print("  [BIN_1, BIN_2, BIN_3, BIN_4] - Central-North")
        print("  [BIN_5, BIN_6, BIN_7] - West")
        print("  [BIN_8, BIN_9, BIN_10] - South")
    
    print(f"\nActual clusters:")
    for cluster_id, cluster_bins in clusters.items():
        bin_ids = [b['id'] for b in cluster_bins]
        print(f"  {bin_ids}")
    
    # Check if we get the expected number of clusters
    expected_count = len(expected)
    actual_count = len(clusters)
    
    if actual_count == expected_count:
        print(f"✅ Cluster count matches expectation ({expected_count})")
    else:
        print(f"❌ Cluster count differs: got {actual_count}, expected {expected_count}")

def main():
    """Main test function"""
    print("=== SIMPLE DYNAMIC CLUSTERING TESTING ===")
    
    # Load test systems
    systems = load_systems()
    
    # Test both systems
    for system_name, system_data in systems.items():
        clusters, info = test_simple_dynamic_clustering(system_name, system_data)
        
        if clusters:
            # Compare with expected results
            compare_with_expected(system_name, clusters)
            
            # Test different depot percentages
            test_with_different_depot_percentages(system_name, system_data)

if __name__ == "__main__":
    main()
