#!/usr/bin/env python3
"""
Final Integration Test for Proactive Cluster Dispatch System
Tests the complete system with real data to verify redundant dispatch prevention.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cleanify', 'simulation-backend'))

import json
from src.services.agent_service import WasteCollectionAgent
from src.repositories.system_repository import SystemRepository
from src.models.bin import WasteBin
from src.models.truck import Truck
from src.models.depot import Depot

def create_test_system():
    """Create a test system with realistic data for proactive dispatch testing"""
    # Create bins in 3 geographical clusters
    bins_data = [
        # North cluster (University area)
        {
            "id": "bin_uni_1", "type": "general", "capacity": 100, "fill_level": 85, 
            "location": {"lat": 52.308, "lng": 4.904}, "disposal_threshold": 80
        },
        {
            "id": "bin_uni_2", "type": "general", "capacity": 100, "fill_level": 82, 
            "location": {"lat": 52.310, "lng": 4.906}, "disposal_threshold": 80
        },
        {
            "id": "bin_uni_3", "type": "general", "capacity": 100, "fill_level": 78, 
            "location": {"lat": 52.306, "lng": 4.902}, "disposal_threshold": 80
        },
        
        # South cluster (Residential area)
        {
            "id": "bin_res_1", "type": "general", "capacity": 100, "fill_level": 90, 
            "location": {"lat": 52.250, "lng": 4.885}, "disposal_threshold": 80
        },
        {
            "id": "bin_res_2", "type": "general", "capacity": 100, "fill_level": 88, 
            "location": {"lat": 52.248, "lng": 4.887}, "disposal_threshold": 80
        },
        {
            "id": "bin_res_3", "type": "general", "capacity": 100, "fill_level": 75, 
            "location": {"lat": 52.252, "lng": 4.883}, "disposal_threshold": 80
        },
        
        # East cluster (Commercial area)
        {
            "id": "bin_com_1", "type": "general", "capacity": 100, "fill_level": 84, 
            "location": {"lat": 52.275, "lng": 4.950}, "disposal_threshold": 80
        },
        {
            "id": "bin_com_2", "type": "general", "capacity": 100, "fill_level": 83, 
            "location": {"lat": 52.277, "lng": 4.952}, "disposal_threshold": 80
        },
        {
            "id": "bin_com_3", "type": "general", "capacity": 100, "fill_level": 76, 
            "location": {"lat": 52.273, "lng": 4.948}, "disposal_threshold": 80
        },
    ]
    
    # Create trucks
    trucks_data = [
        {
            "id": "truck_alpha", "capacity": 800, "current_load": 0, "status": "available",
            "location": {"lat": 52.2728, "lng": 4.9208}  # Central depot
        },
        {
            "id": "truck_beta", "capacity": 800, "current_load": 0, "status": "available",
            "location": {"lat": 52.2728, "lng": 4.9208}  # Central depot
        }
    ]
    
    # Create depot
    depots_data = [
        {
            "id": "central_depot", "location": {"lat": 52.2728, "lng": 4.9208},
            "name": "Central Waste Management Depot"
        }
    ]
    
    return {
        "bins": bins_data,
        "trucks": trucks_data,
        "depots": depots_data,
        "schedules": []
    }

def test_proactive_dispatch_integration():
    """Test the complete proactive dispatch system integration"""
    print("🔬 PROACTIVE CLUSTER DISPATCH INTEGRATION TEST")
    print("=" * 70)
    
    # Create test system
    system_data = create_test_system()
    
    # Initialize repository and agent
    repo = SystemRepository()
    repo.load_system_data(system_data)
    
    agent = WasteCollectionAgent()
    
    print(f"📊 Test System Created:")
    print(f"   🗑️ Bins: {len(system_data['bins'])}")
    print(f"   🚛 Trucks: {len(system_data['trucks'])}")
    print(f"   🏢 Depots: {len(system_data['depots'])}")
    
    # Test clustering
    bins = repo.get_bins()
    clusters = agent.get_or_create_clusters(bins)
    
    print(f"\\n🔍 Clustering Results:")
    print(f"   📊 Created {len(clusters)} clusters")
    for cluster_id, cluster_bins in clusters.items():
        bin_ids = [b['id'] for b in cluster_bins]
        print(f"   Cluster {cluster_id}: {bin_ids}")
    
    # Simulate the problematic scenario
    print(f"\\n🎯 Testing Redundant Dispatch Prevention")
    print("=" * 50)
    
    trucks = repo.get_trucks()
    simulation_time = 1000
    
    # Scenario 1: First bin in North cluster reaches DT
    trigger_bin_1 = next(b for b in bins if b['id'] == 'bin_uni_1')
    print(f"\\n1️⃣ {trigger_bin_1['id']} reaches DT (fill: {trigger_bin_1['fill_level']}%)")
    
    result_1 = agent.handle_bin_reached_dt_with_cluster_optimization(
        trigger_bin_1, bins, trucks, simulation_time
    )
    
    print(f"   Action: {result_1['action']}")
    if result_1.get('truck_id'):
        print(f"   🚛 Truck dispatched: {result_1['truck_id']}")
        print(f"   📦 Bins in route: {[b['id'] for b in result_1.get('bins_to_collect', [])]}")
    
    # Scenario 2: Another bin in same cluster reaches DT shortly after
    trigger_bin_2 = next(b for b in bins if b['id'] == 'bin_uni_2')
    print(f"\\n2️⃣ {trigger_bin_2['id']} reaches DT (same cluster, 30 seconds later)")
    
    result_2 = agent.handle_bin_reached_dt_with_cluster_optimization(
        trigger_bin_2, bins, trucks, simulation_time + 30
    )
    
    print(f"   Action: {result_2['action']}")
    redundant_prevented = result_2['action'] == 'add_to_existing_route'
    
    if redundant_prevented:
        print(f"   ✅ SUCCESS: Redundant dispatch prevented!")
        print(f"   📦 Added to existing collection queue")
    else:
        print(f"   ❌ FAILED: Redundant dispatch occurred")
        if result_2.get('truck_id'):
            print(f"   🚛 Truck dispatched: {result_2['truck_id']}")
    
    # Scenario 3: Bin in different cluster reaches DT
    trigger_bin_3 = next(b for b in bins if b['id'] == 'bin_res_1')
    print(f"\\n3️⃣ {trigger_bin_3['id']} reaches DT (different cluster)")
    
    result_3 = agent.handle_bin_reached_dt_with_cluster_optimization(
        trigger_bin_3, bins, trucks, simulation_time + 60
    )
    
    print(f"   Action: {result_3['action']}")
    cross_cluster_works = result_3['action'] == 'dispatch_truck'
    
    if result_3.get('truck_id'):
        print(f"   🚛 Truck dispatched: {result_3['truck_id']}")
        print(f"   📦 Bins in route: {[b['id'] for b in result_3.get('bins_to_collect', [])]}")
    
    # Get system status
    print(f"\\n📊 System Status After Tests:")
    status = agent.get_proactive_dispatch_status()
    print(f"   Proactive dispatch enabled: {status['proactive_dispatch_enabled']}")
    print(f"   Active assignments: {len(status['active_assignments'])}")
    print(f"   Collection queue size: {status['collection_queue_size']}")
    
    # Test summary
    print(f"\\n📋 Test Results Summary:")
    print("=" * 40)
    print(f"✅ Clusters created: {len(clusters) == 3}")
    print(f"✅ First dispatch works: {result_1['action'] == 'dispatch_truck'}")
    print(f"✅ Redundant dispatch prevented: {redundant_prevented}")
    print(f"✅ Cross-cluster dispatch works: {cross_cluster_works}")
    
    all_tests_passed = all([
        len(clusters) == 3,
        result_1['action'] == 'dispatch_truck',
        redundant_prevented,
        cross_cluster_works
    ])
    
    if all_tests_passed:
        print(f"\\n🎉 ALL INTEGRATION TESTS PASSED!")
        print("   The proactive cluster dispatch system is working correctly.")
        print("   ✅ Clustering creates logical geographical groups")
        print("   ✅ First dispatch triggers normally") 
        print("   ✅ Redundant dispatches are prevented")
        print("   ✅ Cross-cluster dispatches work as expected")
    else:
        print(f"\\n❌ SOME TESTS FAILED")
        print("   Please check the implementation.")
    
    return all_tests_passed

if __name__ == "__main__":
    print("🚀 Starting Proactive Cluster Dispatch Integration Test")
    print("=" * 80)
    
    try:
        success = test_proactive_dispatch_integration()
        
        print(f"\\n{'🎉 INTEGRATION TEST PASSED' if success else '❌ INTEGRATION TEST FAILED'}")
        
        if success:
            print("\\n📈 System Performance Improvements:")
            print("   • Reduced redundant truck dispatches by preventing multiple")
            print("     trucks from being sent to the same cluster")
            print("   • Improved capacity utilization through proactive bin collection")
            print("   • Enhanced clustering creates 3 logical geographical groups")
            print("   • Cluster-aware dispatch coordination prevents waste of resources")
            
        exit(0 if success else 1)
        
    except Exception as e:
        print(f"\\n💥 Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)