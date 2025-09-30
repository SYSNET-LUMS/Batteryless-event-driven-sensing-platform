#!/usr/bin/env python3
"""
Simple debug test for truck movement calculations
"""

def debug_truck_movement():
    print("🔍 DEBUGGING TRUCK MOVEMENT CALCULATIONS")
    print("=" * 50)
    
    # Test parameters
    distance_to_bin = 0.36  # km (360 meters)
    time_step_seconds = 60  # 1 minute
    
    # Fast truck
    fast_speed = 60.0  # km/h
    hours_passed = time_step_seconds / 3600.0  # Convert to hours
    fast_distance_traveled = fast_speed * hours_passed
    
    print(f"Distance to bin: {distance_to_bin:.2f} km")
    print(f"Time step: {time_step_seconds} seconds = {hours_passed:.4f} hours")
    print()
    
    print(f"Fast truck (60 km/h):")
    print(f"  Can travel: {fast_distance_traveled:.4f} km in {time_step_seconds}s")
    print(f"  Will reach bin? {fast_distance_traveled >= distance_to_bin}")
    print(f"  Time needed: {(distance_to_bin/fast_speed)*3600:.1f} seconds")
    
    # Slow truck  
    slow_speed = 30.0  # km/h
    slow_distance_traveled = slow_speed * hours_passed
    
    print(f"\nSlow truck (30 km/h):")
    print(f"  Can travel: {slow_distance_traveled:.4f} km in {time_step_seconds}s")
    print(f"  Will reach bin? {slow_distance_traveled >= distance_to_bin}")
    print(f"  Time needed: {(distance_to_bin/slow_speed)*3600:.1f} seconds")
    
    print(f"\n✅ Both trucks should reach the bin in 1 minute since:")
    print(f"   Fast truck needs: {(distance_to_bin/fast_speed)*60:.1f} minutes")
    print(f"   Slow truck needs: {(distance_to_bin/slow_speed)*60:.1f} minutes")
    print(f"   Both < 1 minute, so both reach bin in first step")
    
    # Test with larger distance
    print(f"\n🧪 TEST WITH LARGER DISTANCE (5 km):")
    large_distance = 5.0  # km
    
    fast_time_needed = (large_distance/fast_speed)*60  # minutes
    slow_time_needed = (large_distance/slow_speed)*60  # minutes
    
    print(f"Distance: {large_distance} km")
    print(f"Fast truck needs: {fast_time_needed:.1f} minutes") 
    print(f"Slow truck needs: {slow_time_needed:.1f} minutes")
    
    # 1-minute steps
    fast_progress_1min = fast_distance_traveled
    slow_progress_1min = slow_distance_traveled
    
    print(f"\nAfter 1 minute:")
    print(f"Fast truck travels: {fast_progress_1min:.2f} km (remaining: {large_distance-fast_progress_1min:.2f} km)")
    print(f"Slow truck travels: {slow_progress_1min:.2f} km (remaining: {large_distance-slow_progress_1min:.2f} km)")

if __name__ == "__main__":
    debug_truck_movement()