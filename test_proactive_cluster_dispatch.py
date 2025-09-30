#!/usr/bin/env python3
"""
Test the Proactive Cluster Dispatch System
Tests the functionality to prevent redundant truck dispatches to the same cluster.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cleanify', 'simulation-backend'))

from src.services.agent_service import WasteCollectionAgent
from src.services.clustering_service import ClusteringService
from src.services.proactive_cluster_dispatch_service import ProactiveClusterDispatchService
from src.config.constants import DISPOSAL_THRESHOLD_MULTIPLIER
import json

def create_test_data():
    """Create test data with 3 clusters"""
    # North cluster (around 52.3, 4.9)
    north_bins = [
        {"id": "bin_north_1", "location": {"lat": 52.30, "lng": 4.90}, "fill_level": 85, "capacity": 100, "disposal_threshold": 80},
        {"id": "bin_north_2", "location": {"lat": 52.31, "lng": 4.91}, "fill_level": 75, "capacity": 100, "disposal_threshold": 80},
        {"id": "bin_north_3", "location": {"lat": 52.29, "lng": 4.89}, "fill_level": 70, "capacity": 100, "disposal_threshold": 80}
    ]
    
    # South cluster (around 52.25, 4.88)
    south_bins = [
        {"id": "bin_south_1", "location": {"lat": 52.25, "lng": 4.88}, "fill_level": 90, "capacity": 100, "disposal_threshold": 80},
        {"id": "bin_south_2", "location": {"lat": 52.24, "lng": 4.89}, "fill_level": 85, "capacity": 100, "disposal_threshold": 80},
        {"id": "bin_south_3", "location": {"lat": 52.26, "lng": 4.87}, "fill_level": 78, "capacity": 100, "disposal_threshold": 80}
    ]
    
    # East cluster (around 52.27, 4.95)
    east_bins = [
        {"id": "bin_east_1", "location": {"lat": 52.27, "lng": 4.95}, "fill_level": 82, "capacity": 100, "disposal_threshold": 80},
        {"id": "bin_east_2", "location": {"lat": 52.28, "lng": 4.96}, "fill_level": 77, "capacity": 100, "disposal_threshold": 80},
        {"id": "bin_east_3", "location": {"lat": 52.26, "lng": 4.94}, "fill_level": 74, "capacity": 100, "disposal_threshold": 80},
        {"id": "bin_east_4", "location": {"lat": 52.275, "lng": 4.955}, "fill_level": 72, "capacity": 100, "disposal_threshold": 80}
    ]
    
    bins = north_bins + south_bins + east_bins
    
    trucks = [
        {"id": "truck_1", "capacity": 800, "current_load": 0, "location": {"lat": 52.2728, "lng": 4.9208}, "status": "available"},
        {"id": "truck_2", "capacity": 800, "current_load": 0, "location": {"lat": 52.2728, "lng": 4.9208}, "status": "available"}
    ]
    
    return bins, trucks

def test_proactive_dispatch():
    """Test proactive cluster dispatch to prevent redundant dispatches"""
    print("🧪 Testing Proactive Cluster Dispatch System")
    print("=" * 60)
    
    # Create test data
    bins, trucks = create_test_data()
    
    # Create agent
    agent = WasteCollectionAgent()
    
    print(f"📍 Created test system with {len(bins)} bins and {len(trucks)} trucks")
    
    # Test clustering first
    print(f"\\n🔍 Testing clustering...")
    clusters = agent.get_or_create_clusters(bins)
    print(f"✅ Created {len(clusters)} clusters:")
    for cluster_id, cluster_bins in clusters.items():
        bin_ids = [b['id'] for b in cluster_bins]
        print(f"   Cluster {cluster_id}: {len(cluster_bins)} bins - {bin_ids}")
    
    # Test scenario: Multiple bins in same cluster reach DT sequentially
    print(f"\\n🎯 Testing redundant dispatch prevention...")
    
    simulation_time = 1000
    
    # First bin reaches DT - should trigger dispatch
    trigger_bin_1 = next(b for b in bins if b['id'] == 'bin_north_1')
    print(f"\\n1️⃣ Bin {trigger_bin_1['id']} reaches DT (fill: {trigger_bin_1['fill_level']}%)")
    
    result_1 = agent.handle_bin_reached_dt_with_cluster_optimization(
        trigger_bin_1, bins, trucks, simulation_time
    )
    
    print(f"   Result: {result_1['action']}")
    if result_1['action'] == 'dispatch_truck':
        print(f"   🚛 Dispatched truck {result_1['truck_id']} to collect {len(result_1['bins_to_collect'])} bins")
        print(f"   📦 Bins to collect: {[b['id'] for b in result_1['bins_to_collect']]}")
    
    # Second bin in same cluster reaches DT - should NOT trigger new dispatch
    trigger_bin_2 = next(b for b in bins if b['id'] == 'bin_north_2')
    trigger_bin_2['fill_level'] = 85  # Make it reach DT
    
    print(f"\\n2️⃣ Bin {trigger_bin_2['id']} reaches DT (fill: {trigger_bin_2['fill_level']}%)")
    
    result_2 = agent.handle_bin_reached_dt_with_cluster_optimization(
        trigger_bin_2, bins, trucks, simulation_time + 50
    )
    
    print(f"   Result: {result_2['action']}")
    if result_2['action'] == 'add_to_existing_route':
        print(f"   ✅ Added to existing route - no redundant dispatch!")
        print(f"   📦 Added bin {trigger_bin_2['id']} to collection queue")
    elif result_2['action'] == 'dispatch_truck':
        print(f"   ❌ FAILED: Redundant dispatch occurred!")
        print(f"   🚛 Dispatched truck {result_2['truck_id']}")
    
    # Test cross-cluster dispatch (should work normally)
    trigger_bin_3 = next(b for b in bins if b['id'] == 'bin_south_1')
    print(f"\\n3️⃣ Bin {trigger_bin_3['id']} reaches DT (different cluster)")
    
    result_3 = agent.handle_bin_reached_dt_with_cluster_optimization(
        trigger_bin_3, bins, trucks, simulation_time + 100
    )
    
    print(f"   Result: {result_3['action']}")
    if result_3['action'] == 'dispatch_truck':
        print(f"   🚛 Dispatched truck {result_3['truck_id']} to different cluster")
        print(f"   📦 Bins to collect: {[b['id'] for b in result_3['bins_to_collect']]}")
    
    # Get proactive dispatch status
    print(f"\\n📊 Proactive Dispatch Status:")
    status = agent.get_proactive_dispatch_status()
    print(f"   Enabled: {status['proactive_dispatch_enabled']}")
    print(f"   Active assignments: {len(status['active_assignments'])}")
    print(f"   Collection queue size: {status['collection_queue_size']}")
    
    print(f"\\n✅ Proactive cluster dispatch test completed!")
    
    return {
        'clusters_created': len(clusters),
        'first_dispatch': result_1['action'] == 'dispatch_truck',
        'redundant_prevented': result_2['action'] == 'add_to_existing_route',
        'cross_cluster_works': result_3['action'] == 'dispatch_truck'
    }

def test_capacity_estimation():
    """Test truck capacity estimation for proactive bin collection"""
    print(f"\\n🧮 Testing Capacity Estimation")
    print("=" * 40)
    
    bins, trucks = create_test_data()
    agent = WasteCollectionAgent()
    
    # Get a cluster
    clusters = agent.get_or_create_clusters(bins)
    north_cluster = list(clusters.values())[0]  # Get first cluster
    
    # Test capacity estimation
    truck = trucks[0]
    current_load = 200  # Already have some load
    
    # Find bins in cluster that could be collected
    trigger_bin = north_cluster[0]
    
    print(f"🚛 Truck capacity: {truck['capacity']}")
    print(f"📦 Current load: {current_load}")
    print(f"🎯 Trigger bin: {trigger_bin['id']} (fill: {trigger_bin['fill_level']})")
    print(f"🏘️ Cluster size: {len(north_cluster)} bins")
    
    # Use the agent's cluster collection logic
    bins_to_collect = agent.collect_bins_from_cluster(
        trigger_bin,
        north_cluster,
        truck['capacity'],
        current_load,
        1000
    )
    
    total_collection = sum(b['fill_level'] for b in [trigger_bin] + bins_to_collect)
    
    print(f"\\n✅ Collection plan:")
    print(f"   Trigger bin: {trigger_bin['id']} ({trigger_bin['fill_level']} units)")
    for bin_data in bins_to_collect:
        print(f"   Additional: {bin_data['id']} ({bin_data['fill_level']} units)")
    print(f"   Total collection: {total_collection} units")
    print(f"   Final load: {current_load + total_collection}/{truck['capacity']}")
    print(f"   Capacity utilization: {((current_load + total_collection) / truck['capacity'] * 100):.1f}%")
    
    return {
        'bins_collected': len(bins_to_collect) + 1,
        'total_collection': total_collection,
        'capacity_utilization': (current_load + total_collection) / truck['capacity']
    }

if __name__ == "__main__":
    print("🚀 Starting Proactive Cluster Dispatch Tests")
    print("=" * 80)
    
    # Test proactive dispatch
    dispatch_results = test_proactive_dispatch()
    
    # Test capacity estimation
    capacity_results = test_capacity_estimation()
    
    # Summary
    print(f"\\n📋 Test Summary")
    print("=" * 40)
    print(f"✅ Clusters created: {dispatch_results['clusters_created']}")
    print(f"✅ First dispatch worked: {dispatch_results['first_dispatch']}")
    print(f"✅ Redundant dispatch prevented: {dispatch_results['redundant_prevented']}")
    print(f"✅ Cross-cluster dispatch works: {dispatch_results['cross_cluster_works']}")
    print(f"✅ Capacity utilization: {capacity_results['capacity_utilization']:.1%}")
    
    # Overall result
    all_passed = all([
        dispatch_results['clusters_created'] == 3,
        dispatch_results['first_dispatch'],
        dispatch_results['redundant_prevented'],
        dispatch_results['cross_cluster_works'],
        capacity_results['capacity_utilization'] < 1.0
    ])
    
    if all_passed:
        print(f"\\n🎉 ALL TESTS PASSED! Proactive cluster dispatch is working correctly.")
    else:
        print(f"\\n❌ Some tests failed. Please check the implementation.")