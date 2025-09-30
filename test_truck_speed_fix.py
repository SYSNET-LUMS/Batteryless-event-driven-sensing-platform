#!/usr/bin/env python3
"""
Test script to verify truck speed is properly used in simulation
"""

import sys
import os
sys.path.append('/media/muneeb-ur-rehman/CA66F1CB66F1B871/Study/Sproj/Cleanify/cleanify/simulation-backend/src')

from services.simulation.simulation_service import SimulationService
from services.routing.enhanced_truck_availability_service import EnhancedTruckAvailabilityService
from services.traffic.predictive_dispatch_service import PredictiveDispatchService

def test_truck_speed_usage():
    """Test that truck speeds are properly used in calculations"""
    print("🧪 TESTING TRUCK SPEED USAGE IN SIMULATION")
    print("=" * 50)
    
    # Test data
    bin_data = {
        'id': 'TEST_BIN',
        'lat': 31.5497,
        'lng': 74.3436,
        'capacity': 500,
        'fillLevel': 80,
        'fillRate': 3.0
    }
    
    depot_data = {
        'id': 'TEST_DEPOT',
        'lat': 31.5200,
        'lng': 74.3500
    }
    
    # Test trucks with different speeds
    fast_truck = {
        'id': 'FAST_TRUCK',
        'speed': 60.0,  # 60 km/h
        'capacity': 100
    }
    
    slow_truck = {
        'id': 'SLOW_TRUCK', 
        'speed': 30.0,  # 30 km/h
        'capacity': 100
    }
    
    # Test simulation service
    print("\n1. Testing SimulationService travel time calculation:")
    sim_service = SimulationService()
    
    # Calculate travel times for both trucks
    fast_travel = sim_service._get_travel_time_to_depot(bin_data, depot_data, fast_truck)
    slow_travel = sim_service._get_travel_time_to_depot(bin_data, depot_data, slow_truck)
    default_travel = sim_service._get_travel_time_to_depot(bin_data, depot_data)  # No truck data
    
    print(f"   Fast truck (60 km/h): {fast_travel:.3f} hours")
    print(f"   Slow truck (30 km/h): {slow_travel:.3f} hours") 
    print(f"   Default speed (40 km/h): {default_travel:.3f} hours")
    
    # Verify the relationship
    if fast_travel < slow_travel:
        print("   ✅ Fast truck has shorter travel time")
    else:
        print("   ❌ Speed relationship incorrect")
    
    # Test truck availability service
    print("\n2. Testing EnhancedTruckAvailabilityService:")
    avail_service = EnhancedTruckAvailabilityService()
    
    from_location = {'lat': 31.5497, 'lng': 74.3436}
    to_location = {'lat': 31.5200, 'lng': 74.3500}
    
    fast_time = avail_service._estimate_travel_time(from_location, to_location, fast_truck)
    slow_time = avail_service._estimate_travel_time(from_location, to_location, slow_truck)
    default_time = avail_service._estimate_travel_time(from_location, to_location)
    
    print(f"   Fast truck (60 km/h): {fast_time:.1f} minutes")
    print(f"   Slow truck (30 km/h): {slow_time:.1f} minutes")
    print(f"   Default speed (40 km/h): {default_time:.1f} minutes")
    
    if fast_time < slow_time:
        print("   ✅ Fast truck has shorter travel time")
    else:
        print("   ❌ Speed relationship incorrect")
    
    # Test predictive dispatch service  
    print("\n3. Testing PredictiveDispatchService:")
    dispatch_service = PredictiveDispatchService()
    
    fast_dispatch_time = dispatch_service._get_base_travel_time_minutes(bin_data, fast_truck)
    slow_dispatch_time = dispatch_service._get_base_travel_time_minutes(bin_data, slow_truck)
    default_dispatch_time = dispatch_service._get_base_travel_time_minutes(bin_data)
    
    print(f"   Fast truck (60 km/h): {fast_dispatch_time:.1f} minutes")
    print(f"   Slow truck (30 km/h): {slow_dispatch_time:.1f} minutes")
    print(f"   Default speed (40 km/h): {default_dispatch_time:.1f} minutes")
    
    if fast_dispatch_time < slow_dispatch_time:
        print("   ✅ Fast truck has shorter travel time")
    else:
        print("   ❌ Speed relationship incorrect")
    
    # Summary
    print("\n" + "=" * 50)
    print("🎯 SPEED USAGE TEST SUMMARY")
    print("=" * 50)
    
    speed_working = (fast_travel < slow_travel and 
                    fast_time < slow_time and 
                    fast_dispatch_time < slow_dispatch_time)
    
    if speed_working:
        print("✅ SUCCESS: Truck speeds are properly used in calculations!")
        print("✅ Fast trucks (60 km/h) consistently show shorter travel times")
        print("✅ Slow trucks (30 km/h) consistently show longer travel times")
        print("✅ The simulation now respects actual truck speed properties")
    else:
        print("❌ ISSUE: Speed calculations may still have problems")
        
    # Real-world time example
    print(f"\n🌍 REAL-WORLD EXAMPLE:")
    print(f"   Distance: ~3.5 km (Lahore city center)")
    print(f"   Fast truck (60 km/h): {fast_time:.1f} min = {fast_time*60:.0f} seconds")
    print(f"   Slow truck (30 km/h): {slow_time:.1f} min = {slow_time*60:.0f} seconds") 
    print(f"   Expected: ~3.5 min at 60 km/h, ~7 min at 30 km/h")

if __name__ == "__main__":
    test_truck_speed_usage()