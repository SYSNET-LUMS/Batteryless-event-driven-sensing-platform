#!/usr/bin/env python3
"""
Integration test for route extension and collection queue management.
Tests that nearby bins collected during truck return trips are properly
added to the collection queue and communicated to the frontend.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../simulation-backend/src'))

from services.agent_service import WasteCollectionAgent
from services.simulation.decision_service import DecisionService
from services.external.vroom_service import VROOMService

def test_route_extension_integration():
    """Test that route extensions are properly processed and added to collection queue"""
    print("\n🧪 TESTING ROUTE EXTENSION INTEGRATION")
    print("=" * 60)
    
    # Create test data with a truck already on route and nearby bins
    trucks_data = [
        {
            'id': 'TRUCK_1',
            'lat': 33.61,
            'lng': 73.06,
            'capacity': 1000,
            'currentLoad': 200,
            'status': 'en_route',
            'route': ['BIN_1', 'BIN_2'],
            'routeIndex': 0,  # Still working on route
            'speed': 50
        },
        {
            'id': 'TRUCK_2', 
            'lat': 33.60,
            'lng': 73.05,
            'capacity': 1000,
            'currentLoad': 0,
            'status': 'idle',
            'speed': 50
        }
    ]
    
    bins_data = [
        # Original route bins
        {'id': 'BIN_1', 'lat': 33.61, 'lng': 73.06, 'fillLevel': 90, 'capacity': 500, 'fillRate': 2, 'threshold': 80},
        {'id': 'BIN_2', 'lat': 33.612, 'lng': 73.061, 'fillLevel': 85, 'capacity': 500, 'fillRate': 3, 'threshold': 80},
        
        # Nearby bins that should be collected during return trip
        {'id': 'BIN_3', 'lat': 33.611, 'lng': 73.062, 'fillLevel': 75, 'capacity': 500, 'fillRate': 4, 'threshold': 80},
        {'id': 'BIN_4', 'lat': 33.613, 'lng': 73.063, 'fillLevel': 78, 'capacity': 500, 'fillRate': 3, 'threshold': 80},
        
        # Far bins that should not be included in extension
        {'id': 'BIN_5', 'lat': 33.59, 'lng': 73.04, 'fillLevel': 82, 'capacity': 500, 'fillRate': 2, 'threshold': 80}
    ]
    
    depot_data = {'id': 'DEPOT_1', 'lat': 33.60, 'lng': 73.05, 'name': 'Main Depot'}
    
    try:
        # Initialize agent
        agent = WasteCollectionAgent()
        
        # Test data
        test_data = {
            'bins_data': bins_data,
            'trucks_data': trucks_data,
            'depots_data': [depot_data],
            'schedules': [],
            'simulation_time': 0
        }
        
        print("📊 Initial collection queue size:", len(agent.collection_queue))
        
        # Get routing decision (this should trigger route extension logic)
        routing_result = agent.get_ai_decision('truck_routing', test_data)
        
        print(f"📋 Routing result: {len(routing_result)} routes generated")
        
        # Check if route extensions were found
        route_extensions_found = False
        extended_bins = []
        
        for route in routing_result:
            print(f"🚛 Route for {route.get('truck_id')}: {route.get('route', [])}")
            
            if 'route_extensions' in route:
                route_extensions_found = True
                for extension in route['route_extensions']:
                    if extension.get('success'):
                        additional_bins = extension.get('additional_bins', [])
                        extended_bins.extend(additional_bins)
                        print(f"   ✅ Extension found: {additional_bins}")
            
            if 'nearby_bins' in route:
                nearby_bin_ids = [b.get('id') for b in route['nearby_bins'] if b.get('id')]
                extended_bins.extend(nearby_bin_ids)
                print(f"   ✅ Nearby bins: {nearby_bin_ids}")
        
        print(f"📊 Final collection queue size: {len(agent.collection_queue)}")
        print(f"📦 Extended bins found: {extended_bins}")
        
        # Test results
        success = True
        
        if route_extensions_found or extended_bins:
            print("✅ Route extensions detected in routing result")
        else:
            print("⚠️  No route extensions found - this may be expected if no suitable nearby bins")
        
        # Check if extended bins were added to collection queue
        queue_contains_extensions = any(bin_id in agent.collection_queue for bin_id in extended_bins)
        if extended_bins and queue_contains_extensions:
            print("✅ Extended bins properly added to collection queue")
        elif extended_bins and not queue_contains_extensions:
            print("❌ Extended bins NOT added to collection queue")
            success = False
        else:
            print("ℹ️  No extended bins to verify in queue")
        
        # Test assignment tracking
        assigned_bins = []
        for bin_data in bins_data:
            if agent.is_bin_assigned(bin_data['id']):
                assigned_bins.append(bin_data['id'])
        
        print(f"🏷️  Assigned bins: {assigned_bins}")
        
        return success
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_collection_queue_updates():
    """Test that collection queue is properly updated with route extensions"""
    print("\n🔄 TESTING COLLECTION QUEUE UPDATES")
    print("=" * 60)
    
    try:
        agent = WasteCollectionAgent()
        
        # Simulate route result with extensions
        mock_routing_result = [
            {
                'truck_id': 'TRUCK_1',
                'route': ['BIN_1', 'BIN_2'],
                'route_extensions': [
                    {
                        'success': True,
                        'additional_bins': ['BIN_3', 'BIN_4'],
                        'extension_type': 'route_extension'
                    }
                ]
            }
        ]
        
        initial_queue_size = len(agent.collection_queue)
        print(f"📊 Initial queue size: {initial_queue_size}")
        
        # Process route extensions
        agent._process_route_extensions(mock_routing_result, 0.0)
        
        final_queue_size = len(agent.collection_queue)
        print(f"📊 Final queue size: {final_queue_size}")
        print(f"📦 Collection queue: {agent.collection_queue}")
        
        # Verify extended bins were added
        if 'BIN_3' in agent.collection_queue and 'BIN_4' in agent.collection_queue:
            print("✅ Extended bins successfully added to collection queue")
            return True
        else:
            print("❌ Extended bins NOT added to collection queue")
            return False
            
    except Exception as e:
        print(f"❌ Collection queue test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 STARTING ROUTE EXTENSION INTEGRATION TESTS")
    
    test1_result = test_route_extension_integration()
    test2_result = test_collection_queue_updates()
    
    print("\n📋 TEST SUMMARY")
    print("=" * 40)
    print(f"Route Extension Integration: {'✅ PASS' if test1_result else '❌ FAIL'}")
    print(f"Collection Queue Updates: {'✅ PASS' if test2_result else '❌ FAIL'}")
    
    if test1_result and test2_result:
        print("\n🎉 ALL TESTS PASSED!")
        print("Route extensions are properly integrated with collection queue management.")
    else:
        print("\n⚠️  SOME TESTS FAILED")
        print("Route extension integration needs further debugging.")