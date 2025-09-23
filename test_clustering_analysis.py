"""
Test Clustering Analysis for Cleanify System

Analyzes clustering behavior with the test_system_high_fill.json data
to understand why bins are being grouped incorrectly.
"""

import sys
import os
import json
import math

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'cleanify', 'simulation-backend', 'src'))

from services.clustering_service import ClusteringService

def haversine_distance(lat1, lng1, lat2, lng2):
    """Calculate distance between two points using Haversine formula"""
    # Convert decimal degrees to radians 
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])

    # Haversine formula 
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371  # Radius of earth in kilometers
    return c * r * 1000  # Convert to meters

def load_test_system():
    """Load the test system data"""
    with open('/media/muneeb-ur-rehman/CA66F1CB66F1B871/Study/Sproj/Cleanify/cleanify/simulation-backend/saved_systems/test_system_high_fill.json', 'r') as f:
        return json.load(f)

def analyze_bin_distances(bins_data):
    """Analyze distances between all bins"""
    print("🔍 BIN DISTANCE ANALYSIS")
    print("="*50)
    
    for i, bin1 in enumerate(bins_data):
        for j, bin2 in enumerate(bins_data):
            if i < j:  # Only calculate each pair once
                distance = haversine_distance(
                    bin1['lat'], bin1['lng'], 
                    bin2['lat'], bin2['lng']
                )
                
                print(f"{bin1['id']} ↔ {bin2['id']}: {distance:.1f} meters")
                print(f"  {bin1['id']}: ({bin1['lat']:.6f}, {bin1['lng']:.6f})")
                print(f"  {bin2['id']}: ({bin2['lat']:.6f}, {bin2['lng']:.6f})")
                print()

def test_clustering_parameters():
    """Test different clustering parameters"""
    system_data = load_test_system()
    bins_data = system_data['bins']
    
    print("🧪 TESTING DIFFERENT CLUSTERING PARAMETERS")
    print("="*60)
    
    # Test different eps values
    eps_values = [200, 300, 500, 1000, 2000]
    min_samples_values = [1, 2, 3]
    
    clustering_service = ClusteringService()
    
    try:
        # Create distance matrix once
        print("Creating distance matrix...")
        distance_matrix = clustering_service.create_bin_distance_matrix(bins_data)
        
        print("\nDistance Matrix:")
        for i, bin1 in enumerate(bins_data):
            for j, bin2 in enumerate(bins_data):
                if i < j:
                    print(f"{bin1['id']} ↔ {bin2['id']}: {distance_matrix[i][j]:.1f}m")
        print()
        
        # Test different parameter combinations
        for eps in eps_values:
            for min_samples in min_samples_values:
                print(f"📊 eps={eps}m, min_samples={min_samples}")
                print("-" * 40)
                
                try:
                    clusters = clustering_service.create_clusters_dbscan(
                        bins_data, distance_matrix, 
                        eps_meters=eps, min_samples=min_samples
                    )
                    
                    cluster_info = clustering_service.get_cluster_info(clusters)
                    
                    print(f"Total clusters: {len(clusters)}")
                    
                    for cluster_id, info in cluster_info.items():
                        bin_ids = info['bin_ids']
                        print(f"  Cluster {cluster_id}: {bin_ids} ({len(bin_ids)} bins)")
                        
                        # Show distances within cluster
                        if len(bin_ids) > 1:
                            cluster_bins = info['bins']
                            for i, bin1 in enumerate(cluster_bins):
                                for j, bin2 in enumerate(cluster_bins):
                                    if i < j:
                                        dist = haversine_distance(
                                            bin1['lat'], bin1['lng'],
                                            bin2['lat'], bin2['lng'] 
                                        )
                                        print(f"    {bin1['id']} ↔ {bin2['id']}: {dist:.1f}m")
                    
                    print()
                    
                except Exception as e:
                    print(f"  ❌ Error: {e}")
                    print()
                
    except Exception as e:
        print(f"❌ Failed to create distance matrix: {e}")
        print("Falling back to Haversine distance analysis...")
        
        # Fallback analysis using Haversine
        for eps in eps_values:
            for min_samples in min_samples_values:
                print(f"📊 FALLBACK: eps={eps}m, min_samples={min_samples}")
                print("-" * 40)
                
                # Manual clustering based on distances
                clusters = simulate_dbscan_clustering(bins_data, eps, min_samples)
                
                print(f"Total clusters: {len(clusters)}")
                for cluster_id, cluster_bins in clusters.items():
                    bin_ids = [b['id'] for b in cluster_bins]
                    print(f"  Cluster {cluster_id}: {bin_ids}")
                print()

def simulate_dbscan_clustering(bins_data, eps, min_samples):
    """Simulate DBSCAN clustering using Haversine distances"""
    n_bins = len(bins_data)
    
    # Create distance matrix using Haversine
    distance_matrix = []
    for i in range(n_bins):
        row = []
        for j in range(n_bins):
            if i == j:
                row.append(0)
            else:
                dist = haversine_distance(
                    bins_data[i]['lat'], bins_data[i]['lng'],
                    bins_data[j]['lat'], bins_data[j]['lng']
                )
                row.append(dist)
        distance_matrix.append(row)
    
    # Simple DBSCAN simulation
    visited = [False] * n_bins
    clusters = {}
    cluster_id = 0
    noise_bins = []
    
    for i in range(n_bins):
        if visited[i]:
            continue
            
        visited[i] = True
        
        # Find neighbors within eps
        neighbors = []
        for j in range(n_bins):
            if i != j and distance_matrix[i][j] <= eps:
                neighbors.append(j)
        
        # If enough neighbors, start a cluster
        if len(neighbors) >= min_samples - 1:  # -1 because we don't count the point itself
            clusters[cluster_id] = [bins_data[i]]
            
            # Add neighbors to cluster
            neighbor_queue = neighbors[:]
            while neighbor_queue:
                neighbor_idx = neighbor_queue.pop(0)
                
                if not visited[neighbor_idx]:
                    visited[neighbor_idx] = True
                    
                    # Find neighbors of this neighbor
                    neighbor_neighbors = []
                    for k in range(n_bins):
                        if neighbor_idx != k and distance_matrix[neighbor_idx][k] <= eps:
                            neighbor_neighbors.append(k)
                    
                    # If this neighbor has enough neighbors, add them to queue
                    if len(neighbor_neighbors) >= min_samples - 1:
                        neighbor_queue.extend([nn for nn in neighbor_neighbors if not visited[nn]])
                
                # Add to cluster if not already in one
                if not any(bins_data[neighbor_idx] in cluster_bins for cluster_bins in clusters.values()):
                    clusters[cluster_id].append(bins_data[neighbor_idx])
            
            cluster_id += 1
        else:
            # Not enough neighbors - noise point
            noise_bins.append(bins_data[i])
    
    # Add noise points as individual clusters
    for noise_bin in noise_bins:
        clusters[cluster_id] = [noise_bin]
        cluster_id += 1
    
    return clusters

def analyze_bin_properties(bins_data):
    """Analyze properties of bins that might affect clustering"""
    print("📋 BIN PROPERTIES ANALYSIS")
    print("="*40)
    
    for bin_data in bins_data:
        print(f"{bin_data['id']}:")
        print(f"  Location: ({bin_data['lat']:.6f}, {bin_data['lng']:.6f})")
        print(f"  Fill Level: {bin_data['fillLevel']}%")
        print(f"  Capacity: {bin_data['capacity']}L")
        print(f"  Threshold: {bin_data['threshold']}%")
        print(f"  Fill Rate: {bin_data['fillRate']}/hour")
        print(f"  Needs Collection: {'Yes' if bin_data['fillLevel'] >= bin_data['threshold'] else 'No'}")
        print()

def main():
    """Main analysis function"""
    print("🔬 CLEANIFY CLUSTERING ANALYSIS")
    print("Analyzing clustering behavior with test_system_high_fill.json")
    print("="*70)
    
    system_data = load_test_system()
    bins_data = system_data['bins']
    
    print(f"System loaded: {len(bins_data)} bins, {len(system_data['trucks'])} trucks")
    print()
    
    # 1. Analyze bin properties
    analyze_bin_properties(bins_data)
    
    # 2. Analyze distances between bins
    analyze_bin_distances(bins_data)
    
    # 3. Test different clustering parameters
    test_clustering_parameters()
    
    # 4. Provide recommendations
    print("🎯 RECOMMENDATIONS")
    print("="*30)
    print("Based on the analysis:")
    print("1. Consider reducing eps parameter if bins are too far apart")
    print("2. Consider reducing min_samples to 1 for small datasets")
    print("3. Check if OSRM service is providing realistic distances")
    print("4. Consider geographic constraints (roads, obstacles)")

if __name__ == "__main__":
    main()