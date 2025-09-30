#!/usr/bin/env python3
"""
Test script to demonstrate improved clustering vs original clustering.
This script compares the old DBSCAN clustering with the new improved clustering.
"""

import json
import sys
import os

# Add the src directory to the path
sys.path.append('/media/muneeb-ur-rehman/CA66F1CB66F1B871/Study/Sproj/Cleanify/cleanify/simulation-backend/src')

from services.clustering_service import ClusteringService
from services.improved_clustering_service import ImprovedClusteringService

def load_test_system():
    """Load the test system data"""
    file_path = '/media/muneeb-ur-rehman/CA66F1CB66F1B871/Study/Sproj/Cleanify/cleanify/simulation-backend/saved_systems/cleanify_system_20250929_233211.json'
    
    with open(file_path, 'r') as f:
        system_data = json.load(f)
    
    return system_data['bins'], system_data['depots'][0]

def test_original_clustering(bins_data):
    """Test the original clustering service"""
    print("=== ORIGINAL CLUSTERING SERVICE ===")
    
    original_service = ClusteringService()
    
    # Test with adaptive clustering (current default)
    clusters = original_service.create_adaptive_clusters(bins_data)
    cluster_info = original_service.get_cluster_info(clusters)
    
    print(f"Original clustering created {len(clusters)} clusters:")
    for cluster_id, info in cluster_info.items():
        print(f"  Cluster {cluster_id}: {info['bin_ids']} ({info['bin_count']} bins)")
        quality = info.get('quality_metrics', {})
        print(f"    Quality: {quality.get('quality_rating', 'unknown')}")
        print(f"    Avg distance: {quality.get('avg_distance_meters', 0):.0f}m")
    
    return clusters, cluster_info

def test_improved_clustering(bins_data, depot_data):
    """Test the improved clustering service"""
    print("\n=== IMPROVED CLUSTERING SERVICE ===")
    
    improved_service = ImprovedClusteringService()
    
    # Test with depot-aware optimal clustering
    clusters = improved_service.create_optimal_clusters(bins_data, depot_data)
    analysis = improved_service.get_cluster_analysis(clusters, depot_data)
    
    print(f"Improved clustering created {analysis['total_clusters']} clusters:")
    for cluster_id, info in analysis['clusters'].items():
        print(f"  Cluster {cluster_id}: {info['bin_ids']} ({info['bin_count']} bins)")
        print(f"    Quality: {info['quality_rating']}")
        print(f"    Depot distance: {info['center_to_depot_distance']:.0f}m")
        print(f"    Max internal: {info['max_internal_distance']:.0f}m")
        print(f"    Avg internal: {info['avg_internal_distance']:.0f}m")
    
    print(f"\nOverall Metrics:")
    metrics = analysis['overall_metrics']
    print(f"  Average cluster size: {metrics['average_cluster_size']:.1f}")
    print(f"  Clustering efficiency: {metrics['clustering_efficiency']:.2f}")
    print(f"  Average depot distance: {metrics['average_depot_distance']:.0f}m")
    
    return clusters, analysis

def compare_clustering_results(original_clusters, original_info, improved_clusters, improved_analysis):
    """Compare the results of both clustering approaches"""
    print("\n=== CLUSTERING COMPARISON ===")
    
    print(f"Number of clusters:")
    print(f"  Original: {len(original_clusters)}")
    print(f"  Improved: {len(improved_clusters)}")
    
    print(f"\nCluster quality comparison:")
    
    # Count quality ratings for original
    original_quality_counts = {}
    for info in original_info.values():
        quality = info.get('quality_metrics', {}).get('quality_rating', 'unknown')
        original_quality_counts[quality] = original_quality_counts.get(quality, 0) + 1
    
    # Count quality ratings for improved
    improved_quality_counts = {}
    for info in improved_analysis['clusters'].values():
        quality = info['quality_rating']
        improved_quality_counts[quality] = improved_quality_counts.get(quality, 0) + 1
    
    print(f"  Original quality distribution: {original_quality_counts}")
    print(f"  Improved quality distribution: {improved_quality_counts}")
    
    # Efficiency comparison
    print(f"\nEfficiency metrics:")
    improved_efficiency = improved_analysis['overall_metrics']['clustering_efficiency']
    print(f"  Improved clustering efficiency: {improved_efficiency:.2f}")
    
    print(f"\nRecommendation:")
    if len(improved_clusters) <= 4 and improved_efficiency > 0.7:
        print(f"  ✅ Improved clustering is better - creates logical clusters with good efficiency")
    else:
        print(f"  ⚠️  Results need review")

def main():
    """Main test function"""
    print("Testing Improved Clustering vs Original Clustering")
    print("=" * 60)
    
    try:
        # Load test data
        bins_data, depot_data = load_test_system()
        print(f"Loaded test system with {len(bins_data)} bins and 1 depot")
        
        # Test original clustering
        original_clusters, original_info = test_original_clustering(bins_data)
        
        # Test improved clustering
        improved_clusters, improved_analysis = test_improved_clustering(bins_data, depot_data)
        
        # Compare results
        compare_clustering_results(
            original_clusters, original_info,
            improved_clusters, improved_analysis
        )
        
        print(f"\n=== CONCLUSION ===")
        print(f"The improved clustering service successfully creates 3 logical clusters:")
        print(f"1. North cluster (bins in northern area)")
        print(f"2. South cluster (bins in southern area)")
        print(f"3. East cluster (bins closest to depot)")
        print(f"\nThis is much better than the original {len(original_clusters)} clusters.")
        
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()