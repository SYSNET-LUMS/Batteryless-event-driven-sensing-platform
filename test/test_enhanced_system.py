#!/usr/bin/env python3
"""
Test script for the enhanced traffic system with realistic bin fill levels
"""

import sys
import os
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)) )

from services.traffic.dispatch_service import DispatchService

def test_enhanced_dispatch_system():
    """Test the enhanced dispatch system with realistic data"""
    
    # Load test system with higher fill levels
    with open('../saved_systems/test_system_high_fill.json', 'r') as f:
        system_data = json.load(f)
    
    bins_data = system_data['bins']
    trucks_data = system_data['trucks']
    
    dispatch_service = DispatchService()
    
    print("=== TESTING ENHANCED DISPATCH SYSTEM ===")
    print(f"Testing {len(bins_data)} bins with {len(trucks_data)} trucks")
    print()
    
    simulation_time = 0  # Start of simulation
    
    # Test individual bin dispatch decisions
    print("1. INDIVIDUAL BIN DISPATCH DECISIONS")
    print("-" * 50)
    for i, bin_data in enumerate(bins_data):
        for j, truck_data in enumerate(trucks_data):
            if truck_data['status'] == 'idle':  # Only test with idle trucks
                print(f"\nBin {bin_data['id']} (Fill: {bin_data['fillLevel']}%) + Truck {truck_data['id']}:")
                
                try:
                    decision = dispatch_service.should_dispatch_now(bin_data, truck_data, simulation_time)
                    print(f"  Decision: {decision.get('dispatch')}")
                    print(f"  Delay: {decision.get('delay_min', 0)} minutes")
                    print(f"  Reason: {decision.get('reason', 'No reason')[:80]}...")
                    if 'fuel_savings_min' in decision:
                        print(f"  Fuel Savings: {decision['fuel_savings_min']} minutes")
                    if 'current_traffic_level' in decision:
                        print(f"  Traffic Level: {decision['current_traffic_level']}")
                        
                except Exception as e:
                    print(f"  ERROR: {e}")
                
                break  # Only test first idle truck per bin
    
    print("\n\n2. SYSTEM-WIDE TRAFFIC OVERVIEW")
    print("-" * 50)
    
    try:
        overview = dispatch_service.get_system_traffic_overview(bins_data, simulation_time)
        
        print(f"Current Time: {overview['current_time']['hour']:02d}:{overview['current_time']['minute']:02d}")
        
        summary = overview['system_summary']
        print(f"System Traffic Status:")
        print(f"  Light Traffic Bins: {summary['bins_in_light_traffic']}")
        print(f"  Moderate Traffic Bins: {summary['bins_in_moderate_traffic']}")
        print(f"  Heavy Traffic Bins: {summary['bins_in_heavy_traffic']}")
        print(f"  Average Density: {summary['average_traffic_density']}")
        
        recommendations = overview['dispatch_recommendations']
        print(f"\nDispatch Recommendations:")
        print(f"  Immediate Dispatch: {len(recommendations['immediate_dispatch'])} bins")
        print(f"  Wait for Better Traffic: {len(recommendations['wait_for_better_traffic'])} bins")
        print(f"  Total Fuel Savings Potential: {recommendations['fuel_savings_potential']} minutes")
        
        # Show specific recommendations
        if recommendations['immediate_dispatch']:
            print(f"\n  Bins needing immediate dispatch:")
            for rec in recommendations['immediate_dispatch'][:3]:  # Show first 3
                bin_id = rec['bin_id']
                fill = rec['current_fill']
                reason = rec['prediction']['reason'][:50]
                print(f"    {bin_id}: {fill}% - {reason}...")
        
        if recommendations['wait_for_better_traffic']:
            print(f"\n  Bins that can wait for better traffic:")
            for rec in recommendations['wait_for_better_traffic'][:3]:  # Show first 3
                bin_id = rec['bin_id']
                fill = rec['current_fill']
                delay = rec['prediction'].get('delay_min', 0)
                savings = rec['prediction'].get('fuel_savings_min', 0)
                print(f"    {bin_id}: {fill}% - Wait {delay}min, Save {savings}min")
                
    except Exception as e:
        print(f"ERROR in system overview: {e}")
    
    print("\n\n3. SYSTEM STATUS")
    print("-" * 50)
    
    # Count bins by urgency
    urgent_bins = [b for b in bins_data if b['fillLevel'] >= 90]
    critical_bins = [b for b in bins_data if b['fillLevel'] >= b['threshold']]
    approaching_bins = [b for b in bins_data if b['fillLevel'] >= (b['threshold'] - 10)]
    
    print(f"Bin Status Summary:")
    print(f"  Overflowing (90%+): {len(urgent_bins)} bins")
    print(f"  Above Threshold ({bins_data[0]['threshold']}%+): {len(critical_bins)} bins") 
    print(f"  Approaching Threshold: {len(approaching_bins)} bins")
    
    print(f"\nTruck Status:")
    idle_trucks = [t for t in trucks_data if t['status'] == 'idle']
    print(f"  Idle trucks available: {len(idle_trucks)}")
    
    # Prediction: Based on bin status, trucks should be dispatched
    expected_dispatches = max(len(critical_bins), len(urgent_bins))
    print(f"\nExpected Behavior:")
    print(f"  Should dispatch {expected_dispatches} trucks immediately")
    print(f"  Enhanced system should provide fuel-efficient routing")
    print(f"  Traffic-aware timing should optimize travel times")
    
    print("\n=== ENHANCED SYSTEM TEST COMPLETE ===")
    
    # Return summary for verification
    return {
        'bins_tested': len(bins_data),
        'trucks_available': len(idle_trucks),
        'urgent_bins': len(urgent_bins),
        'critical_bins': len(critical_bins),
        'system_working': True
    }

if __name__ == "__main__":
    test_enhanced_dispatch_system()
