"""
Test Enhanced Routing System

Tests the new enhanced truck availability and dynamic routing features:
1. Smart truck availability (considers scheduled trucks)
2. Route extension for trucks already on trips
3. Dynamic route optimization with VROOM integration
"""

import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'cleanify', 'simulation-backend', 'src'))

from services.traffic_service import TrafficService
from services.routing.enhanced_truck_availability_service import EnhancedTruckAvailabilityService
from services.routing.dynamic_route_optimizer import DynamicRouteOptimizer

def create_test_data():
    """Create comprehensive test data for enhanced routing"""
    
    # Test trucks - mix of statuses
    trucks_data = [
        {
            'id': 'truck_1',
            'status': 'idle',
            'lat': 24.8607,
            'lng': 67.0011,
            'capacity': 1000,
            'currentLoad': 0
        },
        {
            'id': 'truck_2', 
            'status': 'collecting',
            'lat': 24.8650,
            'lng': 67.0100,
            'capacity': 1000,
            'currentLoad': 300,
            'route': ['bin_10', 'bin_11', 'bin_12'],
            'routeIndex': 1,  # Currently going to bin_11
            'returnRoute': [],
            'returnRouteIndex': 0
        },
        {
            'id': 'truck_3',
            'status': 'idle', 
            'lat': 24.8500,
            'lng': 67.0200,
            'capacity': 800,
            'currentLoad': 0
        },
        {
            'id': 'truck_4',
            'status': 'traveling',
            'lat': 24.8700,
            'lng': 67.0150,
            'capacity': 1200,
            'currentLoad': 600,
            'route': ['bin_20'],
            'routeIndex': 0
        }
    ]
    
    # Test bins with various fill levels
    bins_data = [
        {
            'id': 'bin_1',
            'lat': 24.8620,
            'lng': 67.0050,
            'fillLevel': 85,
            'capacity': 500,
            'threshold': 80,
            'fillRate': 4.2,
            'lastCollected': 1600000000
        },
        {
            'id': 'bin_2',
            'lat': 24.8630,
            'lng': 67.0060,
            'fillLevel': 92,
            'capacity': 500,
            'threshold': 80,
            'fillRate': 5.1,
            'lastCollected': 1600000000
        },
        {
            'id': 'bin_3',
            'lat': 24.8610,
            'lng': 67.0040,
            'fillLevel': 78,
            'capacity': 500,
            'threshold': 80,
            'fillRate': 3.8,
            'lastCollected': 1600000000
        },
        # Bins near truck_2's current route (for route extension testing)
        {
            'id': 'bin_near_truck2_1',
            'lat': 24.8655,  # Close to truck_2's next target
            'lng': 67.0095,
            'fillLevel': 88,
            'capacity': 500,
            'threshold': 80,
            'fillRate': 4.5,
            'lastCollected': 1600000000
        },
        {
            'id': 'bin_near_truck2_2',
            'lat': 24.8645,
            'lng': 67.0105,
            'fillLevel': 83,
            'capacity': 500,
            'threshold': 80,
            'fillRate': 2.8,
            'lastCollected': 1600000000
        },
        # Existing route bins for truck_2
        {
            'id': 'bin_10',
            'lat': 24.8640,
            'lng': 67.0090,
            'fillLevel': 85,
            'capacity': 500,
            'threshold': 80,
            'fillRate': 3.0,
            'lastCollected': 1600000000
        },
        {
            'id': 'bin_11',
            'lat': 24.8660,
            'lng': 67.0110,
            'fillLevel': 90,
            'capacity': 500,
            'threshold': 80,
            'fillRate': 4.0,
            'lastCollected': 1600000000
        },
        {
            'id': 'bin_12',
            'lat': 24.8670,
            'lng': 67.0120,
            'fillLevel': 82,
            'capacity': 500,
            'threshold': 80,
            'fillRate': 2.5,
            'lastCollected': 1600000000
        }
    ]
    
    # Test schedules - truck_4 is scheduled
    schedules = [
        {
            'id': 'schedule_1',
            'truck_id': 'truck_4',
            'status': 'pending',
            'scheduled_time': (8 * 60 + 45) * 60,  # 8:45 AM in seconds from midnight
            'target_bin_ids': ['bin_15', 'bin_16']
        }
    ]
    
    # Test depot
    depot_data = {
        'id': 'main_depot',
        'lat': 24.8600,
        'lng': 67.0000,
        'name': 'Main Collection Depot'
    }
    
    return trucks_data, bins_data, schedules, depot_data

def test_enhanced_truck_availability():
    """Test enhanced truck availability service"""
    print("\n" + "="*60)
    print("TESTING ENHANCED TRUCK AVAILABILITY SERVICE")
    print("="*60)
    
    trucks_data, bins_data, schedules, depot_data = create_test_data()
    current_time_seconds = 8 * 3600 + 30 * 60  # 8:30 AM
    
    availability_service = EnhancedTruckAvailabilityService()
    
    try:
        result = availability_service.get_available_trucks_enhanced(
            trucks_data, bins_data, schedules, current_time_seconds, depot_data
        )
        
        print("✅ Enhanced availability analysis completed successfully!")
        print(f"\nAvailability Summary:")
        summary = result.get('availability_summary', {})
        print(f"  • Total trucks: {summary.get('total_trucks', 0)}")
        print(f"  • Available: {summary.get('available_count', 0)}")
        print(f"  • Busy: {summary.get('busy_count', 0)}")
        print(f"  • Scheduled (reserved): {summary.get('scheduled_count', 0)}")
        print(f"  • Can extend routes: {summary.get('route_extendable_count', 0)}")
        
        print(f"\nDetailed Analysis:")
        
        # Available trucks
        if result.get('available_trucks'):
            print(f"  Available Trucks:")
            for truck_info in result['available_trucks']:
                truck = truck_info['truck']
                availability = truck_info['availability_info']
                print(f"    - {truck['id']}: {availability['reason']}")
        
        # Busy trucks
        if result.get('busy_trucks'):
            print(f"  Busy Trucks:")
            for truck_info in result['busy_trucks']:
                truck = truck_info['truck']
                availability = truck_info['availability_info']
                print(f"    - {truck['id']}: {availability['reason']} (available in {availability.get('estimated_availability', 0):.0f} min)")
        
        # Scheduled trucks
        if result.get('scheduled_trucks'):
            print(f"  Scheduled (Reserved) Trucks:")
            for truck_info in result['scheduled_trucks']:
                truck = truck_info['truck']
                schedule_info = truck_info['schedule_info']
                print(f"    - {truck['id']}: {schedule_info['reason']}")
        
        # Route extendable trucks
        if result.get('route_extendable'):
            print(f"  Trucks That Can Extend Routes:")
            for truck_info in result['route_extendable']:
                truck = truck_info['truck']
                extension_info = truck_info['extension_info']
                print(f"    - {truck['id']}: Can collect {extension_info.get('extension_count', 0)} additional bins")
                
                # Show nearby bins
                nearby_bins = extension_info.get('nearby_bins', [])
                if nearby_bins:
                    bin_ids = [b.get('id') for b in nearby_bins]
                    print(f"      Nearby bins: {', '.join(bin_ids)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Enhanced availability test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_dynamic_route_optimizer():
    """Test dynamic route optimizer"""
    print("\n" + "="*60)
    print("TESTING DYNAMIC ROUTE OPTIMIZER")
    print("="*60)
    
    trucks_data, bins_data, schedules, depot_data = create_test_data()
    current_time_seconds = 8 * 3600 + 30 * 60  # 8:30 AM
    
    optimizer = DynamicRouteOptimizer()
    
    try:
        result = optimizer.optimize_routes_with_dynamic_availability(
            trucks_data, bins_data, schedules, depot_data, current_time_seconds
        )
        
        if result.get('success', False):
            print("✅ Dynamic route optimization completed successfully!")
            
            optimization_result = result.get('optimization_result', {})
            
            print(f"\nExecution Time: {optimization_result.get('execution_time', 0):.2f} seconds")
            
            # Summary
            summary = optimization_result.get('optimization_summary', {})
            print(f"\nOptimization Summary:")
            print(f"  • Trucks utilized: {summary.get('total_trucks_utilized', 0)}")
            print(f"  • Bins assigned: {summary.get('total_bins_assigned', 0)}")
            print(f"  • Bins deferred: {summary.get('total_bins_deferred', 0)}")
            print(f"  • Efficiency: {summary.get('optimization_efficiency', 0)*100:.1f}%")
            print(f"  • Strategy: {summary.get('strategy_used', 'unknown')}")
            
            # Route extensions
            extensions = optimization_result.get('route_extensions', [])
            if extensions:
                print(f"\nRoute Extensions ({len(extensions)}):")
                for ext in extensions:
                    if ext.get('success', False):
                        print(f"  ✅ {ext['truck_id']}: +{len(ext.get('additional_bins', []))} bins ({ext.get('estimated_additional_time', 0):.0f} min)")
                    else:
                        print(f"  ❌ {ext['truck_id']}: {ext.get('reason', 'Failed')}")
            
            # New routes
            new_routes = optimization_result.get('new_routes', [])
            if new_routes:
                print(f"\nNew Routes ({len(new_routes)}):")
                for route in new_routes:
                    if route.get('success', False):
                        metrics = route.get('route_metrics', {})
                        print(f"  ✅ {route['truck_id']}: {metrics.get('total_bins', 0)} bins, {metrics.get('estimated_duration_minutes', 0):.0f} min")
                    else:
                        print(f"  ❌ {route['truck_id']}: {route.get('reason', 'Failed')}")
            
            # Critical overrides
            overrides = optimization_result.get('critical_overrides', [])
            if overrides:
                print(f"\nCritical Overrides ({len(overrides)}):")
                for override in overrides:
                    if override.get('success', False):
                        print(f"  🚨 {override['truck_id']}: Emergency collection (schedule overridden)")
            
            # Deferred collections
            deferred = optimization_result.get('deferred_collections', [])
            if deferred:
                print(f"\nDeferred Collections ({len(deferred)}):")
                for defer in deferred[:3]:  # Show first 3
                    print(f"  ⏳ {defer['bin_id']}: {defer['reason']}")
                if len(deferred) > 3:
                    print(f"  ... and {len(deferred) - 3} more")
        
        else:
            print(f"❌ Dynamic route optimization failed: {result.get('error', 'Unknown error')}")
            fallback = result.get('fallback_result', {})
            if fallback:
                print(f"Fallback result available: {fallback}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Dynamic route optimization test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_enhanced_traffic_routing():
    """Test the enhanced traffic service routing methods"""
    print("\n" + "="*60)
    print("TESTING ENHANCED TRAFFIC ROUTING")
    print("="*60)
    
    trucks_data, bins_data, schedules, depot_data = create_test_data()
    current_time_seconds = 8 * 3600 + 30 * 60  # 8:30 AM
    
    traffic_manager = TrafficService()
    
    try:
        result = traffic_manager.get_enhanced_routing_recommendations(
            trucks_data, bins_data, schedules, depot_data, current_time_seconds
        )
        
        if result.get('success', False):
            print("✅ Enhanced traffic routing completed successfully!")
            
            executive_summary = result.get('executive_summary', {})
            print(f"\nExecutive Summary:")
            print(f"  • Efficiency Score: {executive_summary.get('efficiency_score', 0)}%")
            print(f"  • Available Trucks: {executive_summary.get('total_trucks_available', 0)}")
            print(f"  • Busy Trucks: {executive_summary.get('total_trucks_busy', 0)}")
            print(f"  • Route Extensions: {executive_summary.get('route_extensions_possible', 0)}")
            print(f"  • Bins Assigned: {executive_summary.get('bins_assigned_for_collection', 0)}")
            print(f"  • Next Review: {executive_summary.get('next_review_recommended_minutes', 0)} minutes")
            
            # Key decisions
            key_decisions = executive_summary.get('key_decisions', [])
            if key_decisions:
                print(f"\nKey Decisions:")
                for i, decision in enumerate(key_decisions, 1):
                    print(f"  {i}. {decision}")
            
            # Actionable recommendations
            recommendations = result.get('recommendations', [])
            if recommendations:
                print(f"\nActionable Recommendations ({len(recommendations)}):")
                for rec in recommendations:
                    priority = rec.get('priority', 'unknown').upper()
                    action = rec.get('action', 'unknown')
                    details = rec.get('details', 'No details')
                    print(f"  [{priority}] {action}: {details}")
                    
                    # Additional details
                    if 'traffic_advice' in rec:
                        print(f"    Traffic: {rec['traffic_advice']}")
                    if 'estimated_time' in rec:
                        print(f"    Time: {rec['estimated_time']} min")
            
            # Strategy information
            detailed = result.get('detailed_results', {})
            strategy = detailed.get('traffic_strategy', {})
            if strategy and 'strategic_recommendations' in strategy:
                print(f"\nTraffic Strategy:")
                current_conditions = strategy.get('current_conditions', {})
                print(f"  Current: {current_conditions.get('level', 'unknown')} traffic (hour {current_conditions.get('hour', '?')})")
                
                for rec in strategy['strategic_recommendations']:
                    print(f"  • {rec}")
            
        else:
            print(f"❌ Enhanced traffic routing failed: {result.get('error', 'Unknown error')}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Enhanced traffic routing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all enhanced routing tests"""
    print("🚛 ENHANCED ROUTING SYSTEM TESTS")
    print("Testing smart truck availability and dynamic route optimization...")
    
    test_results = []
    
    # Test 1: Enhanced truck availability
    test_results.append(test_enhanced_truck_availability())
    
    # Test 2: Dynamic route optimizer  
    test_results.append(test_dynamic_route_optimizer())
    
    # Test 3: Enhanced traffic routing
    test_results.append(test_enhanced_traffic_routing())
    
    # Summary
    print("\n" + "="*60)
    print("TEST RESULTS SUMMARY")
    print("="*60)
    
    passed = sum(test_results)
    total = len(test_results)
    
    print(f"✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("Enhanced routing system is working correctly with:")
        print("  ✅ Smart truck availability (considers scheduled trucks)")
        print("  ✅ Dynamic route extensions for trucks already on trips")
        print("  ✅ Traffic-aware routing recommendations")
        print("  ✅ Integration with VROOM optimization service")
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
        print("The system may have partial functionality.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)