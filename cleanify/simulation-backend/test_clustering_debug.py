#!/usr/bin/env python3
"""
Test script to debug clustering logic issues.
"""

import sys
import os
import json
import logging

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from services.clustering_service import ClusteringService
from services.improved_clustering_service import ImprovedClusteringService
from utils.distance import calculate_haversine_distance
import numpy as np

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def load_test_system():
    """Load the latest system for testing"""
    system_file = "saved_systems/cleanify_system_20251007_130200.json"
    with open(system_file, 'r') as f:
        return json.load(f)

def analyze_bin_distances(bins_data):
    """Analyze distances between all bins"""
    print(f"\n=== BIN DISTANCE ANALYSIS ===")
    print(f"Total bins: {len(bins_data)}")
    
    distances = []
    for i in range(len(bins_data)):
        for j in range(i + 1, len(bins_data)):
            bin1, bin2 = bins_data[i], bins_data[j]
            dist = calculate_haversine_distance(
                bin1['lat'], bin1['lng'],
                bin2['lat'], bin2['lng']
            )
            distances.append({
                'bin1': bin1['id'],
                'bin2': bin2['id'],
                'distance_m': round(dist, 1),
                'bin1_coords': (round(bin1['lat'], 6), round(bin1['lng'], 6)),
                'bin2_coords': (round(bin2['lat'], 6), round(bin2['lng'], 6))
            })
    
    # Sort by distance
    distances.sort(key=lambda x: x['distance_m'])
    
    print(f"\nClosest bin pairs:")
    for i, d in enumerate(distances[:10]):
        print(f"  {i+1}. {d['bin1']} ↔ {d['bin2']}: {d['distance_m']}m")
    
    print(f"\nFarthest bin pairs:")
    for i, d in enumerate(distances[-5:]):
        print(f"  {d['bin1']} ↔ {d['bin2']}: {d['distance_m']}m")
    
    # Distance statistics
    dist_values = [d['distance_m'] for d in distances]
    print(f"\nDistance Statistics:")
    print(f"  Min: {min(dist_values):.1f}m")
    print(f"  Max: {max(dist_values):.1f}m")
    print(f"  Mean: {np.mean(dist_values):.1f}m")
    print(f"  Median: {np.median(dist_values):.1f}m")
    print(f"  25th percentile: {np.percentile(dist_values, 25):.1f}m")
    print(f"  75th percentile: {np.percentile(dist_values, 75):.1f}m")
    
    return distances

def test_clustering_with_different_thresholds(bins_data):
    """Test clustering with different distance thresholds"""
    print(f"\n=== CLUSTERING THRESHOLD TESTING ===")
    
    # Test different thresholds
    thresholds = [300, 500, 600, 800, 1000, 1200, 1500, 2000]
    
    for threshold in thresholds:
        print(f"\n--- Testing threshold: {threshold}m ---")
        
        # Create distance matrix
        n = len(bins_data)
        distance_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                if i != j:
                    distance = calculate_haversine_distance(
                        bins_data[i]['lat'], bins_data[i]['lng'],
                        bins_data[j]['lat'], bins_data[j]['lng']
                    )
                    distance_matrix[i][j] = distance
        
        # Test with DBSCAN
        from sklearn.cluster import DBSCAN
        clustering = DBSCAN(eps=threshold, min_samples=1, metric='precomputed')
        cluster_labels = clustering.fit_predict(distance_matrix)
        
        # Analyze results
        unique_labels = set(cluster_labels)
        n_clusters = len(unique_labels) - (1 if -1 in cluster_labels else 0)
        n_noise = list(cluster_labels).count(-1)
        
        print(f"  Clusters: {n_clusters}, Noise points: {n_noise}")
        
        # Show cluster composition
        clusters = {}
        for i, label in enumerate(cluster_labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(bins_data[i]['id'])
        
        for label, bin_ids in clusters.items():
            if label == -1:
                print(f"  Noise: {bin_ids}")
            else:
                print(f"  Cluster {label}: {bin_ids} (size: {len(bin_ids)})")

def test_current_clustering_services(bins_data):
    """Test both clustering services with the current data"""
    print(f"\n=== CURRENT CLUSTERING SERVICES TEST ===")
    
    # Test ClusteringService
    print(f"\n--- ClusteringService (DBSCAN-based) ---")
    clustering_service = ClusteringService()
    
    try:
        # Test adaptive clustering
        clusters1 = clustering_service.create_adaptive_clusters(bins_data)
        print(f"Adaptive clustering created {len(clusters1)} clusters:")
        for cluster_id, cluster_bins in clusters1.items():
            bin_ids = [b['id'] for b in cluster_bins]
            print(f"  Cluster {cluster_id}: {bin_ids} (size: {len(bin_ids)})")
            
            # Calculate cluster quality
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
        
        # Get cluster info
        cluster_info = clustering_service.get_cluster_info(clusters1)
        print(f"\nCluster quality metrics:")
        for cluster_id, info in cluster_info.items():
            quality = info.get('quality_metrics', {})
            print(f"  Cluster {cluster_id}: {quality.get('quality_rating', 'unknown')} "
                  f"(compactness: {quality.get('compactness_score', 'N/A')}, "
                  f"efficiency: {quality.get('collection_efficiency', 'N/A')})")
    
    except Exception as e:
        print(f"Error with ClusteringService: {e}")
    
    # Test ImprovedClusteringService
    print(f"\n--- ImprovedClusteringService (Connectivity-based) ---")
    improved_clustering = ImprovedClusteringService()
    
    try:
        clusters2 = improved_clustering.create_optimal_clusters(bins_data)
        print(f"Improved clustering created {len(clusters2)} clusters:")
        for cluster_id, cluster_bins in clusters2.items():
            bin_ids = [b['id'] for b in cluster_bins]
            print(f"  Cluster {cluster_id}: {bin_ids} (size: {len(bin_ids)})")
            
            # Calculate cluster quality
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
        analysis = improved_clustering.get_cluster_analysis(clusters2)
        print(f"\nImproved clustering metrics:")
        for cluster_id, info in analysis['clusters'].items():
            quality = info.get('quality_rating', 'unknown')
            max_dist = info.get('max_internal_distance', 'N/A')
            print(f"  Cluster {cluster_id}: {quality} (max distance: {max_dist}m)")
    
    except Exception as e:
        print(f"Error with ImprovedClusteringService: {e}")

def compare_clustering_methods(bins_data):
    """Compare different clustering approaches"""
    print(f"\n=== CLUSTERING METHOD COMPARISON ===")
    
    # Manual geographical clustering for comparison
    print(f"\n--- Manual Geographical Analysis ---")
    print("Based on coordinates, logical geographical clusters should be:")
    
    # Group by approximate geographical areas (rough analysis)
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
    
    print(f"  North area (lat > 33.615): {north_bins}")
    print(f"  Central area (33.58 < lat < 33.615): {central_bins}")
    print(f"  South area (lat < 33.58): {south_bins}")

def main():
    """Main test function"""
    print("=== CLUSTERING LOGIC DEBUGGING ===")
    
    # Load test system
    system = load_test_system()
    bins_data = system['bins']
    
    print(f"Loaded system with {len(bins_data)} bins")
    
    # Analyze distances between bins
    distances = analyze_bin_distances(bins_data)
    
    # Test different clustering thresholds
    test_clustering_with_different_thresholds(bins_data)
    
    # Test current clustering services
    test_current_clustering_services(bins_data)
    
    # Compare with manual geographical analysis
    compare_clustering_methods(bins_data)

if __name__ == "__main__":
    main()