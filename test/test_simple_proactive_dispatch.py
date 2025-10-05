#!/usr/bin/env python3
"""
Simple test to verify the proactive cluster dispatch concept works.
This test demonstrates the core logic without complex module dependencies.
"""

from math import radians, cos, sin, asin, sqrt
from typing import List, Dict, Any

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate haversine distance between two points in meters"""
    R = 6371000  # Earth radius in meters
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    
    return R * c

def create_clusters(bins: List[Dict], distance_threshold: float = 600) -> Dict[int, List[Dict]]:
    """Create clusters using connectivity-based approach"""
    clusters = {}
    bin_to_cluster = {}
    cluster_id = 0
    
    for bin_data in bins:
        if bin_data['id'] in bin_to_cluster:
            continue
            
        # Start new cluster
        cluster_bins = [bin_data]
        bin_to_cluster[bin_data['id']] = cluster_id
        
        # Find all connected bins using BFS
        queue = [bin_data]
        processed = {bin_data['id']}
        
        while queue:
            current_bin = queue.pop(0)
            
            for other_bin in bins:
                if other_bin['id'] in processed:
                    continue
                
                distance = haversine_distance(
                    current_bin['location']['lat'], current_bin['location']['lng'],
                    other_bin['location']['lat'], other_bin['location']['lng']
                )
                
                if distance <= distance_threshold:
                    cluster_bins.append(other_bin)
                    bin_to_cluster[other_bin['id']] = cluster_id
                    queue.append(other_bin)
                    processed.add(other_bin['id'])
        
        clusters[cluster_id] = cluster_bins
        cluster_id += 1
    
    return clusters

def find_bin_cluster(bin_id: str, clusters: Dict[int, List[Dict]]) -> int:
    """Find which cluster a bin belongs to"""
    for cluster_id, cluster_bins in clusters.items():
        if any(b['id'] == bin_id for b in cluster_bins):
            return cluster_id
    return -1

def estimate_proactive_collection(trigger_bin: Dict, cluster_bins: List[Dict], 
                                truck_capacity: int, current_load: int) -> List[Dict]:
    """Estimate which additional bins can be collected proactively"""
    available_capacity = truck_capacity - current_load - trigger_bin['fill_level']
    
    # Find bins that can be collected (above disposal threshold)
    collectible_bins = [
        b for b in cluster_bins 
        if b['id'] != trigger_bin['id'] and b['fill_level'] >= b.get('disposal_threshold', 80)
    ]
    
    # Sort by fill level (collect fullest first)
    collectible_bins.sort(key=lambda x: x['fill_level'], reverse=True)
    
    selected_bins = []
    total_collection = 0
    
    for bin_data in collectible_bins:
        if total_collection + bin_data['fill_level'] <= available_capacity:
            selected_bins.append(bin_data)
            total_collection += bin_data['fill_level']
    
    return selected_bins

def test_proactive_dispatch_logic():
    """Test the core proactive dispatch logic"""
    print("🧪 Testing Proactive Cluster Dispatch Logic")
    print("=" * 60)
    
    # Create test data with 3 clusters
    bins = [
        # North cluster
        {"id": "bin_north_1", "location": {"lat": 52.30, "lng": 4.90}, "fill_level": 85, "disposal_threshold": 80},
        {"id": "bin_north_2", "location": {"lat": 52.31, "lng": 4.91}, "fill_level": 82, "disposal_threshold": 80},
        {"id": "bin_north_3", "location": {"lat": 52.29, "lng": 4.89}, "fill_level": 78, "disposal_threshold": 80},
        
        # South cluster  
        {"id": "bin_south_1", "location": {"lat": 52.25, "lng": 4.88}, "fill_level": 90, "disposal_threshold": 80},
        {"id": "bin_south_2", "location": {"lat": 52.24, "lng": 4.89}, "fill_level": 85, "disposal_threshold": 80},
        {"id": "bin_south_3", "location": {"lat": 52.26, "lng": 4.87}, "fill_level": 75, "disposal_threshold": 80},
        
        # East cluster
        {"id": "bin_east_1", "location": {"lat": 52.27, "lng": 4.95}, "fill_level": 83, "disposal_threshold": 80},
        {"id": "bin_east_2", "location": {"lat": 52.28, "lng": 4.96}, "fill_level": 81, "disposal_threshold": 80},
        {"id": "bin_east_3", "location": {"lat": 52.26, "lng": 4.94}, "fill_level": 79, "disposal_threshold": 80},
    ]
    
    # Test clustering
    print("\\n🔍 Testing clustering...")
    clusters = create_clusters(bins, distance_threshold=2000)  # Increased threshold
    print(f"✅ Created {len(clusters)} clusters:")
    for cluster_id, cluster_bins in clusters.items():
        bin_ids = [b['id'] for b in cluster_bins]
        print(f"   Cluster {cluster_id}: {bin_ids}")
    
    # Simulate dispatch tracking
    active_dispatches = {}  # cluster_id -> truck_id
    
    # Scenario 1: First bin reaches DT
    trigger_bin = bins[0]  # bin_north_1
    cluster_id = find_bin_cluster(trigger_bin['id'], clusters)
    
    print(f"\\n1️⃣ Bin {trigger_bin['id']} reaches DT (cluster {cluster_id})")
    
    if cluster_id not in active_dispatches:
        # No active dispatch - create new one
        truck_id = "truck_1"
        active_dispatches[cluster_id] = truck_id
        
        # Find proactive bins to collect
        cluster_bins = clusters[cluster_id]
        proactive_bins = estimate_proactive_collection(
            trigger_bin, cluster_bins, truck_capacity=800, current_load=0
        )
        
        print(f"   🚛 Dispatching truck {truck_id}")
        print(f"   📦 Trigger bin: {trigger_bin['id']} ({trigger_bin['fill_level']} units)")
        print(f"   📦 Proactive collection: {[b['id'] for b in proactive_bins]}")
        total_collection = trigger_bin['fill_level'] + sum(b['fill_level'] for b in proactive_bins)
        print(f"   📊 Total collection: {total_collection} units")
        
        action_1 = "dispatch_truck"
    else:
        action_1 = "add_to_existing_route"
    
    # Scenario 2: Second bin in same cluster reaches DT
    trigger_bin_2 = bins[1]  # bin_north_2
    cluster_id_2 = find_bin_cluster(trigger_bin_2['id'], clusters)
    
    print(f"\\n2️⃣ Bin {trigger_bin_2['id']} reaches DT (cluster {cluster_id_2})")
    
    if cluster_id_2 not in active_dispatches:
        print(f"   🚛 Would dispatch new truck - REDUNDANT!")
        action_2 = "dispatch_truck"
    else:
        print(f"   ✅ Cluster already has active dispatch (truck {active_dispatches[cluster_id_2]})")
        print(f"   📦 Adding bin to existing collection route")
        action_2 = "add_to_existing_route"
    
    # Scenario 3: Bin in different cluster reaches DT
    trigger_bin_3 = bins[3]  # bin_south_1
    cluster_id_3 = find_bin_cluster(trigger_bin_3['id'], clusters)
    
    print(f"\\n3️⃣ Bin {trigger_bin_3['id']} reaches DT (cluster {cluster_id_3})")
    
    if cluster_id_3 not in active_dispatches:
        truck_id = "truck_2"
        active_dispatches[cluster_id_3] = truck_id
        print(f"   🚛 Dispatching truck {truck_id} to different cluster")
        action_3 = "dispatch_truck"
    else:
        action_3 = "add_to_existing_route"
    
    # Test results
    print(f"\\n📊 Results Summary:")
    print(f"   Clusters created: {len(clusters)}")
    print(f"   Action 1 (first bin): {action_1}")
    print(f"   Action 2 (same cluster): {action_2}")
    print(f"   Action 3 (different cluster): {action_3}")
    print(f"   Active dispatches: {active_dispatches}")
    
    # Validate results
    success = (
        len(clusters) == 3 and
        action_1 == "dispatch_truck" and
        action_2 == "add_to_existing_route" and
        action_3 == "dispatch_truck"
    )
    
    if success:
        print(f"\\n🎉 SUCCESS: Proactive dispatch logic works correctly!")
        print("   ✅ Created 3 logical clusters")
        print("   ✅ First dispatch triggered normally")
        print("   ✅ Redundant dispatch prevented")
        print("   ✅ Cross-cluster dispatch works")
    else:
        print(f"\\n❌ FAILED: Logic needs adjustment")
    
    return success

if __name__ == "__main__":
    success = test_proactive_dispatch_logic()
    print(f"\\n{'🎉 TEST PASSED' if success else '❌ TEST FAILED'}")