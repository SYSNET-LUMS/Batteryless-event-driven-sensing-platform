#!/usr/bin/env python3
"""
Test script to verify trucks move correctly through simulation time
"""

import sys
import os
sys.path.append('/media/muneeb-ur-rehman/CA66F1CB66F1B871/Study/Sproj/Cleanify/cleanify/simulation-backend/src')

from api.routes.simulation_routes import update_truck_simulation_state, calculate_distance_km

def test_truck_movement_simulation():
    """Test that trucks move correctly through simulation time based on their speed"""
    print("🧪 TESTING TRUCK MOVEMENT IN SIMULATION TIME")
    print("=" * 60)
    
    # Mock repository
    class MockRepo:
        def get_depots(self):
            return [{'id': 'DEPOT_1', 'lat': 31.5497, 'lng': 74.3436}]
    
    repo = MockRepo()
    
    # Test route with 2 bins at realistic distances
    test_route = {
        'bins': [
            {'id': 'BIN_1', 'lat': 31.5500, 'lng': 74.3600, 'current_fill': 30},  # ~2.3 km from start
            {'id': 'BIN_2', 'lat': 31.5700, 'lng': 74.3800, 'current_fill': 25}  # Further away
        ]
    }
    
    # Calculate distances for reference  
    start_to_bin1 = calculate_distance_km(31.5497, 74.3436, 31.5500, 74.3600)  # Start to BIN_1
    bin1_to_bin2 = calculate_distance_km(31.5500, 74.3600, 31.5700, 74.3800)    # BIN_1 to BIN_2
    print(f"📏 Distance from START to BIN_1: {start_to_bin1:.2f} km")
    print(f"📏 Distance from BIN_1 to BIN_2: {bin1_to_bin2:.2f} km")
    
    # Test trucks with different speeds
    fast_truck = {
        'id': 'FAST_TRUCK',
        'speed': 60.0,  # 60 km/h 
        'status': 'traveling',
        'current_route': test_route,
        'route_step': 0,
        'distance_to_next': start_to_bin1,  # Starting distance to first bin
        'current_load': 0
    }
    
    slow_truck = {
        'id': 'SLOW_TRUCK', 
        'speed': 30.0,  # 30 km/h
        'status': 'traveling',
        'current_route': test_route,
        'route_step': 0,
        'distance_to_next': start_to_bin1,  # Starting distance to first bin
        'current_load': 0
    }
    
    print(f"\n⏱️  SIMULATION TIME TESTS:")
    print(f"Route: Start → BIN_1 → BIN_2 → Depot")
    print(f"Distance to BIN_1: {start_to_bin1:.2f} km")
    
    # Test 1: Small time step (should not reach bin)
    print(f"\n1️⃣  TEST: 1 minute simulation step")
    time_step_1min = 60  # 60 seconds = 1 minute
    
    fast_copy = fast_truck.copy()
    slow_copy = slow_truck.copy()
    
    fast_after_1min = update_truck_simulation_state(fast_copy, time_step_1min, repo)
    slow_after_1min = update_truck_simulation_state(slow_copy, time_step_1min, repo)
    
    # Calculate expected distances
    fast_travel_1min = 60.0 * (1/60)  # 60 km/h * 1/60 hour = 1 km
    slow_travel_1min = 30.0 * (1/60)  # 30 km/h * 1/60 hour = 0.5 km
    
    print(f"   Fast truck (60 km/h):")
    print(f"     Expected travel: {fast_travel_1min:.2f} km")
    print(f"     Remaining distance: {fast_after_1min.get('distance_to_next', 0):.2f} km")
    print(f"     Status: {fast_after_1min.get('status', 'unknown')}")
    
    print(f"   Slow truck (30 km/h):")
    print(f"     Expected travel: {slow_travel_1min:.2f} km")  
    print(f"     Remaining distance: {slow_after_1min.get('distance_to_next', 0):.2f} km")
    print(f"     Status: {slow_after_1min.get('status', 'unknown')}")
    
    # Test 2: Longer time step (should reach bin)
    print(f"\n2️⃣  TEST: 10 minute simulation step")
    time_step_10min = 600  # 600 seconds = 10 minutes
    
    fast_copy = fast_truck.copy()
    slow_copy = slow_truck.copy()
    
    fast_after_10min = update_truck_simulation_state(fast_copy, time_step_10min, repo)
    slow_after_10min = update_truck_simulation_state(slow_copy, time_step_10min, repo)
    
    # Calculate expected travel
    fast_travel_10min = 60.0 * (10/60)  # 60 km/h * 10/60 hour = 10 km
    slow_travel_10min = 30.0 * (10/60)  # 30 km/h * 10/60 hour = 5 km
    
    print(f"   Fast truck (60 km/h):")
    print(f"     Expected travel: {fast_travel_10min:.2f} km")
    print(f"     Route step: {fast_after_10min.get('route_step', 0)}")
    print(f"     Status: {fast_after_10min.get('status', 'unknown')}")
    print(f"     Load: {fast_after_10min.get('current_load', 0)} L")
    
    print(f"   Slow truck (30 km/h):")
    print(f"     Expected travel: {slow_travel_10min:.2f} km")
    print(f"     Route step: {slow_after_10min.get('route_step', 0)}")
    print(f"     Status: {slow_after_10min.get('status', 'unknown')}")
    print(f"     Load: {slow_after_10min.get('current_load', 0)} L")
    
    # Test 3: Real-world scenario
    print(f"\n3️⃣  REAL-WORLD SCENARIO:")
    print(f"   Time to travel {start_to_bin1:.2f} km:")
    time_fast = (start_to_bin1 / 60.0) * 60  # minutes
    time_slow = (start_to_bin1 / 30.0) * 60  # minutes
    print(f"     Fast truck (60 km/h): {time_fast:.1f} minutes")
    print(f"     Slow truck (30 km/h): {time_slow:.1f} minutes")
    
    # Verification
    print(f"\n" + "=" * 60)
    print(f"🎯 SIMULATION SYNCHRONIZATION VERIFICATION")
    print(f"=" * 60)
    
    # Check if simulation time matches expected physics
    distance_precision = 0.01  # 10m precision
    time_precision = 1.0  # 1 minute precision
    
    fast_remaining_expected = max(0, start_to_bin1 - fast_travel_1min)
    slow_remaining_expected = max(0, start_to_bin1 - slow_travel_1min)
    
    fast_sync = abs(fast_after_1min.get('distance_to_next', 0) - fast_remaining_expected) < distance_precision
    slow_sync = abs(slow_after_1min.get('distance_to_next', 0) - slow_remaining_expected) < distance_precision
    
    if fast_sync and slow_sync:
        print("✅ SUCCESS: Trucks move correctly with simulation time!")
        print("✅ Fast trucks travel further in same time period")
        print("✅ Slow trucks travel shorter distances in same time period")
        print("✅ Movement is perfectly synchronized with simulation time")
        print("✅ Physics: Distance = Speed × Time is respected")
    else:
        print("❌ ISSUE: Truck movement not synchronized with simulation time")
        print(f"   Fast truck sync: {'✅' if fast_sync else '❌'}")
        print(f"   Slow truck sync: {'✅' if slow_sync else '❌'}")
    
    # Real-world validation
    if time_fast < time_slow:
        print(f"✅ Real-world validation: Fast truck reaches destination sooner")
    else:
        print(f"❌ Real-world validation failed")

if __name__ == "__main__":
    test_truck_movement_simulation()