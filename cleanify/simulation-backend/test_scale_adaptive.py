#!/usr/bin/env python3
"""
Test the scale-adaptive clustering service.
"""

import sys
import os
import json
import logging

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from services.scale_adaptive_clustering_service import ScaleAdaptiveClusteringService
from utils.distance import calculate_haversine_distance

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def load_systems():
    """Load both systems for testing"""
    systems = {}
    
    # Problematic system (small scale)
    with open("saved_systems/cleanify_system_20250819_002311.json", 'r') as f:
        systems['small'] = json.load(f)
    
    # Previous system (larger scale)
    with open("saved_systems/cleanify_system_20251007_130200.json", 'r') as f:
        systems['large'] = json.load(f)
    
    return systems

def test_scale_adaptive_clustering(system_name, system_data):
    """Test the scale-adaptive clustering service"""
    print(f"\n=== TESTING SCALE-ADAPTIVE CLUSTERING: {system_name.upper()} SYSTEM ===")
    
    bins_data = system_data['bins']
    depot_data = system_data.get('depots', [{}])[0] if system_data.get('depots') else None
    
    clustering_service = ScaleAdaptiveClusteringService()
    
    try:
        # Get scale analysis first
        scale_analysis = clustering_service.get_scale_analysis(bins_data)
        print(f"\nScale Analysis:")
        print(f"  Detected scale: {scale_analysis['detected_scale']}")
        print(f"  Description: {scale_analysis['scale_description']}")
        print(f"  Geographical span: {scale_analysis['geographical_span_m']:.0f}m")
        print(f"  Optimal threshold: {scale_analysis['optimal_threshold_m']:.0f}m")
        print(f"  Max cluster size: {scale_analysis['max_cluster_size']}")
        print(f"  Distance stats: Min={scale_analysis['distance_stats']['min_m']:.0f}m, "
              f"Median={scale_analysis['distance_stats']['median_m']:.0f}m, "
              f"Max={scale_analysis['distance_stats']['max_m']:.0f}m")
        
        # Create clusters
        clusters = clustering_service.create_scale_adaptive_clusters(bins_data, depot_data)
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
        for cluster_id, info in cluster_info.items():
            quality = info.get('quality_metrics', {})
            rating = quality.get('quality_rating', 'unknown')
            compactness = quality.get('compactness_score', 0)
            efficiency = quality.get('collection_efficiency', 0)
            print(f"    Cluster {cluster_id}: {rating} (compactness: {compactness:.2f}, efficiency: {efficiency:.2f})")
        
        return clusters, scale_analysis
        
    except Exception as e:
        print(f"Error with ScaleAdaptiveClusteringService: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def compare_clustering_approaches(system_name, bins_data):
    """Compare the scale-adaptive approach with others"""
    print(f"\n=== CLUSTERING COMPARISON: {system_name.upper()} ===")
    
    # Import other services
    from services.fixed_clustering_service import FixedClusteringService
    from services.improved_clustering_service import ImprovedClusteringService
    
    services = [
        ("Scale-Adaptive", ScaleAdaptiveClusteringService()),
        ("Fixed (1300m)", FixedClusteringService()),
        ("Improved (600m)", ImprovedClusteringService())
    ]
    
    results = {}
    
    for name, service in services:
        try:
            if hasattr(service, 'create_scale_adaptive_clusters'):
                clusters = service.create_scale_adaptive_clusters(bins_data)
            elif hasattr(service, 'create_geographical_clusters'):
                clusters = service.create_geographical_clusters(bins_data)
            elif hasattr(service, 'create_optimal_clusters'):
                clusters = service.create_optimal_clusters(bins_data)
            else:
                clusters = service.create_adaptive_clusters(bins_data)
            
            results[name] = {
                'cluster_count': len(clusters),
                'clusters': clusters
            }
            
            print(f"\n{name}:")
            print(f"  Clusters created: {len(clusters)}")
            for cluster_id, cluster_bins in clusters.items():
                bin_ids = [b['id'] for b in cluster_bins]
                print(f"    Cluster {cluster_id}: {bin_ids}")
                
        except Exception as e:
            print(f"  Error with {name}: {e}")
            results[name] = {'error': str(e)}
    
    return results

def test_different_scales():
    """Test the service with different geographical scales"""
    print(f"\n=== TESTING DIFFERENT SCALES ===")
    
    # Create synthetic test data for different scales
    test_scales = [
        {
            'name': 'Local Scale (Parking Lot)',
            'bins': [
                {'id': 'BIN_1', 'lat': 33.6911, 'lng': 73.0260, 'fillLevel': 50, 'capacity': 500},
                {'id': 'BIN_2', 'lat': 33.6912, 'lng': 73.0261, 'fillLevel': 60, 'capacity': 500},  # ~100m
                {'id': 'BIN_3', 'lat': 33.6915, 'lng': 73.0265, 'fillLevel': 40, 'capacity': 500},  # ~500m
            ]
        },
        {
            'name': 'City Scale (Lahore)',
            'bins': [
                {'id': 'BIN_1', 'lat': 31.5804, 'lng': 74.3587, 'fillLevel': 50, 'capacity': 500},  # Lahore center
                {'id': 'BIN_2', 'lat': 31.4504, 'lng': 74.2723, 'fillLevel': 60, 'capacity': 500},  # ~20km south
                {'id': 'BIN_3', 'lat': 31.6204, 'lng': 74.4587, 'fillLevel': 40, 'capacity': 500},  # ~15km northeast
            ]
        },
        {
            'name': 'National Scale (Pakistan)',
            'bins': [
                {'id': 'BIN_1', 'lat': 31.5804, 'lng': 74.3587, 'fillLevel': 50, 'capacity': 500},  # Lahore
                {'id': 'BIN_2', 'lat': 24.8607, 'lng': 67.0011, 'fillLevel': 60, 'capacity': 500},  # Karachi
                {'id': 'BIN_3', 'lat': 33.6844, 'lng': 73.0479, 'fillLevel': 40, 'capacity': 500},  # Islamabad
            ]
        }
    ]
    
    clustering_service = ScaleAdaptiveClusteringService()
    
    for test_data in test_scales:
        print(f"\n--- {test_data['name']} ---")
        bins_data = test_data['bins']
        
        # Get scale analysis
        scale_analysis = clustering_service.get_scale_analysis(bins_data)
        print(f"  Detected scale: {scale_analysis['detected_scale']}")
        print(f"  Span: {scale_analysis['geographical_span_m']:.0f}m")
        print(f"  Threshold: {scale_analysis['optimal_threshold_m']:.0f}m")
        
        # Create clusters
        clusters = clustering_service.create_scale_adaptive_clusters(bins_data)
        print(f"  Clusters: {len(clusters)}")
        for cluster_id, cluster_bins in clusters.items():
            bin_ids = [b['id'] for b in cluster_bins]
            print(f"    Cluster {cluster_id}: {bin_ids}")

def main():
    """Main test function"""
    print("=== SCALE-ADAPTIVE CLUSTERING TESTING ===")
    
    # Load test systems
    systems = load_systems()
    
    # Test both systems
    for system_name, system_data in systems.items():
        clusters, scale_analysis = test_scale_adaptive_clustering(system_name, system_data)
        
        if clusters:
            # Compare with other approaches
            compare_clustering_approaches(system_name, system_data['bins'])
    
    # Test different scales
    test_different_scales()

if __name__ == "__main__":
    main()