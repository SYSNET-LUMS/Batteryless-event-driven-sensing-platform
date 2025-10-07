#!/usr/bin/env python3
"""
Test the fixed clustering service.
"""

import sys
import os
import json
import logging

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from services.fixed_clustering_service import FixedClusteringService
from utils.distance import calculate_haversine_distance

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def load_test_system():
    """Load the latest system for testing"""
    system_file = "saved_systems/cleanify_system_20251007_130200.json"
    with open(system_file, 'r') as f:
        return json.load(f)

def test_fixed_clustering(bins_data):
    """Test the fixed clustering service"""
    print(f"\n=== TESTING FIXED CLUSTERING SERVICE ===")
    
    fixed_clustering = FixedClusteringService()
    
    try:
        clusters = fixed_clustering.create_geographical_clusters(bins_data)
        print(f"Fixed clustering created {len(clusters)} clusters:")
        
        for cluster_id, cluster_bins in clusters.items():
            bin_ids = [b['id'] for b in cluster_bins]
            print(f"  Cluster {cluster_id}: {bin_ids} (size: {len(bin_ids)})")
            
            # Calculate cluster center and quality
            if len(cluster_bins) > 0:
                center_lat = sum(b['lat'] for b in cluster_bins) / len(cluster_bins)
                center_lng = sum(b['lng'] for b in cluster_bins) / len(cluster_bins)
                print(f"    Center: ({center_lat:.6f}, {center_lng:.6f})")
                
                if len(cluster_bins) > 1:
                    max_dist = 0
                    for i in range(len(cluster_bins)):
                        for j in range(i + 1, len(cluster_bins)):
                            dist = calculate_haversine_distance(
                                cluster_bins[i]['lat'], cluster_bins[i]['lng'],
                                cluster_bins[j]['lat'], cluster_bins[j]['lng']
                            )
                            max_dist = max(max_dist, dist)
                    print(f"    Max internal distance: {max_dist:.1f}m")
        
        # Get cluster analysis
        analysis = fixed_clustering.get_cluster_analysis(clusters)
        print(f"\nFixed clustering analysis:")
        print(f"  Total clusters: {analysis['total_clusters']}")
        print(f"  Average cluster size: {analysis['overall_metrics']['average_cluster_size']:.1f}")
        print(f"  Clustering efficiency: {analysis['overall_metrics']['clustering_efficiency']:.2f}")
        
        print(f"\nCluster quality ratings:")
        for cluster_id, info in analysis['clusters'].items():
            quality = info.get('quality_rating', 'unknown')
            max_dist = info.get('max_internal_distance', 'N/A')
            print(f"  Cluster {cluster_id}: {quality} (max distance: {max_dist}m)")
        
        return clusters
    
    except Exception as e:
        print(f"Error with FixedClusteringService: {e}")
        return None

def compare_with_geographical_expectation(clusters, bins_data):
    """Compare results with geographical expectation"""
    print(f"\n=== COMPARISON WITH GEOGRAPHICAL EXPECTATION ===")
    
    # Expected geographical clusters
    north_bins = []  # lat > 33.615
    central_bins = []  # 33.58 < lat < 33.615
    south_bins = []  # lat < 33.58
    
    for bin_data in bins_data:
        lat = bin_data['lat']
        if lat > 33.615:
            north_bins.append(bin_data['id'])
        elif lat > 33.58:
            central_bins.append(bin_data['id'])
        else:
            south_bins.append(bin_data['id'])
    
    print(f"Expected geographical clusters:")
    print(f"  North area (lat > 33.615): {north_bins}")
    print(f"  Central area (33.58 < lat < 33.615): {central_bins}")
    print(f"  South area (lat < 33.58): {south_bins}")
    
    print(f"\nActual clusters from fixed clustering:")
    for cluster_id, cluster_bins in clusters.items():
        bin_ids = [b['id'] for b in cluster_bins]
        print(f"  Cluster {cluster_id}: {bin_ids}")
    
    # Check how well actual clusters match geographical expectations
    print(f"\nCluster matching analysis:")
    
    # Create sets for easy comparison
    expected_clusters = [set(north_bins), set(central_bins), set(south_bins)]
    actual_clusters = [set(b['id'] for b in cluster_bins) for cluster_bins in clusters.values()]
    
    for i, expected in enumerate(expected_clusters):
        if not expected:
            continue
        area_name = ["North", "Central", "South"][i]
        print(f"  {area_name} area ({expected}):")
        
        # Find which actual clusters contain these bins
        for j, actual in enumerate(actual_clusters):
            overlap = expected & actual
            if overlap:
                coverage = len(overlap) / len(expected) * 100
                print(f"    Cluster {j} contains {overlap} ({coverage:.0f}% coverage)")

def main():
    """Main test function"""
    print("=== TESTING FIXED CLUSTERING LOGIC ===")
    
    # Load test system
    system = load_test_system()
    bins_data = system['bins']
    
    print(f"Loaded system with {len(bins_data)} bins")
    
    # Test fixed clustering
    clusters = test_fixed_clustering(bins_data)
    
    if clusters:
        # Compare with geographical expectation
        compare_with_geographical_expectation(clusters, bins_data)

if __name__ == "__main__":
    main()