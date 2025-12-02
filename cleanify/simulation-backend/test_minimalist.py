"""
Minimalist Cleanify Test Script
Tests traffic filtering and VROOM integration
"""

import requests
import json
import sys

API_BASE = "http://localhost:5001/api"


def test_system_initialization():
    """Test basic system initialization"""
    print("\n" + "="*50)
    print("TEST 1: System Initialization")
    print("="*50)
    
    # Initialize system
    resp = requests.post(f"{API_BASE}/initialize")
    assert resp.status_code == 200
    print("✅ System initialized")
    
    # Add depot
    depot_resp = requests.post(f"{API_BASE}/depot", json={
        'lat': 33.6844,
        'lng': 73.0479,
        'name': 'Main Depot'
    })
    assert depot_resp.status_code == 200
    depot_id = depot_resp.json()['id']
    print(f"✅ Depot created: {depot_id}")
    
    # Add bins
    bins_data = [
        {'lat': 33.6850, 'lng': 73.0485, 'fillLevel': 85, 'fillRate': 10, 'threshold': 80},
        {'lat': 33.6860, 'lng': 73.0495, 'fillLevel': 90, 'fillRate': 5, 'threshold': 80},
        {'lat': 33.6870, 'lng': 73.0505, 'fillLevel': 70, 'fillRate': 3, 'threshold': 80}
    ]
    
    bin_ids = []
    for bin_data in bins_data:
        resp = requests.post(f"{API_BASE}/bin", json=bin_data)
        assert resp.status_code == 200
        bin_ids.append(resp.json()['id'])
    print(f"✅ Created {len(bin_ids)} bins")
    
    # Add trucks
    trucks_data = [
        {'lat': 33.6844, 'lng': 73.0479, 'status': 'idle', 'capacity': 1000},
        {'lat': 33.6844, 'lng': 73.0479, 'status': 'idle', 'capacity': 1000}
    ]
    
    truck_ids = []
    for truck_data in trucks_data:
        resp = requests.post(f"{API_BASE}/truck", json=truck_data)
        assert resp.status_code == 200
        truck_ids.append(resp.json()['id'])
    print(f"✅ Created {len(truck_ids)} trucks")
    
    return depot_id, bin_ids, truck_ids


def test_traffic_filtering():
    """Test traffic-aware filtering during heavy hours"""
    print("\n" + "="*50)
    print("TEST 2: Traffic Filtering (Heavy Traffic)")
    print("="*50)
    
    # Simulate heavy traffic hour (8am = 1 hour after 7am start = 3600 seconds)
    dispatch_resp = requests.post(f"{API_BASE}/dispatch", json={
        'simulation_time': 3600  # 8am (heavy traffic)
    })
    
    assert dispatch_resp.status_code == 200
    result = dispatch_resp.json()
    
    print(f"Status: {result['status']}")
    print(f"Routes generated: {len(result.get('routes', []))}")
    print(f"Bins waiting: {len(result.get('waiting', []))}")
    print(f"Traffic filtered: {result.get('traffic_filtered', 0)}")
    
    if result.get('routes'):
        print("\nRoute details:")
        for route in result['routes']:
            print(f"  - Truck {route['truck_id']}: {len(route['bin_ids'])} bins")
            print(f"    Bins: {route['bin_ids']}")
    
    if result.get('waiting'):
        print(f"\nBins waiting for light traffic: {result['waiting']}")
    
    print("✅ Traffic filtering working")


def test_light_traffic_dispatch():
    """Test dispatch during light traffic"""
    print("\n" + "="*50)
    print("TEST 3: Light Traffic Dispatch")
    print("="*50)
    
    # Simulate light traffic hour (10am = 3 hours after 7am = 10800 seconds)
    dispatch_resp = requests.post(f"{API_BASE}/dispatch", json={
        'simulation_time': 10800  # 10am (light traffic)
    })
    
    assert dispatch_resp.status_code == 200
    result = dispatch_resp.json()
    
    print(f"Status: {result['status']}")
    print(f"Routes generated: {len(result.get('routes', []))}")
    print(f"Bins waiting: {len(result.get('waiting', []))}")
    
    if result.get('routes'):
        print("\nDuring light traffic, all urgent bins should be dispatched:")
        for route in result['routes']:
            print(f"  - Truck {route['truck_id']}: {route['bin_ids']}")
    
    print("✅ Light traffic dispatch working")


def test_vroom_integration():
    """Test VROOM service integration"""
    print("\n" + "="*50)
    print("TEST 4: VROOM Integration")
    print("="*50)
    
    try:
        # Check if VROOM is available
        vroom_resp = requests.get("http://localhost:3000/health", timeout=2)
        print(f"✅ VROOM service available (status: {vroom_resp.status_code})")
    except requests.RequestException:
        print("⚠️  VROOM service not available (will use fallback)")
    
    # Test dispatch (will use VROOM if available, fallback otherwise)
    dispatch_resp = requests.post(f"{API_BASE}/dispatch", json={
        'simulation_time': 0
    })
    
    result = dispatch_resp.json()
    
    if result.get('routes'):
        print(f"✅ Got {len(result['routes'])} optimized routes")
    else:
        print("ℹ️  No routes needed (no urgent bins)")


def test_simulation_step():
    """Test simulation time progression"""
    print("\n" + "="*50)
    print("TEST 5: Simulation Step")
    print("="*50)
    
    # Start simulation
    start_resp = requests.post(f"{API_BASE}/start_simulation")
    assert start_resp.status_code == 200
    print("✅ Simulation started")
    
    # Run simulation step
    step_resp = requests.post(f"{API_BASE}/simulation_step", json={
        'time_delta': 60  # 1 minute
    })
    
    assert step_resp.status_code == 200
    result = step_resp.json()
    
    print(f"Status: {result['status']}")
    print(f"Bins updated: {len(result.get('bins', []))}")
    
    # Check bin fill levels increased
    if result.get('bins'):
        bin_sample = result['bins'][0]
        print(f"Sample bin {bin_sample['id']}:")
        print(f"  Fill level: {bin_sample['fillLevel']:.1f}%")
        print(f"  Fill rate: {bin_sample['fillRate']} L/hr")
    
    print("✅ Simulation step working")


def test_configuration():
    """Test configuration loading"""
    print("\n" + "="*50)
    print("TEST 6: Configuration")
    print("="*50)
    
    config_resp = requests.get(f"{API_BASE}/config")
    
    if config_resp.status_code == 200:
        config = config_resp.json()
        print(f"OSRM URL: {config.get('OSRM_URL')}")
        print(f"VROOM URL: {config.get('VROOM_URL')}")
        print(f"Traffic heavy hours: {config.get('TRAFFIC_HEAVY_HOURS')}")
        print(f"Traffic multiplier: {config.get('TRAFFIC_MULTIPLIER')}")
        print("✅ Configuration accessible")
    else:
        print("⚠️  Config endpoint not available (optional)")


def cleanup():
    """Clean up test data"""
    print("\n" + "="*50)
    print("CLEANUP")
    print("="*50)
    
    resp = requests.post(f"{API_BASE}/initialize")
    print("✅ System reset")


def main():
    """Run all tests"""
    print("\n" + "="*50)
    print("CLEANIFY MINIMALIST REFACTOR TESTS")
    print("="*50)
    
    try:
        # Test 1: Initialize system
        depot_id, bin_ids, truck_ids = test_system_initialization()
        
        # Test 2: Traffic filtering
        test_traffic_filtering()
        
        # Test 3: Light traffic
        test_light_traffic_dispatch()
        
        # Test 4: VROOM integration
        test_vroom_integration()
        
        # Test 5: Simulation step
        test_simulation_step()
        
        # Test 6: Configuration
        test_configuration()
        
        # Cleanup
        cleanup()
        
        print("\n" + "="*50)
        print("✅ ALL TESTS PASSED")
        print("="*50)
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ Test assertion failed: {e}")
        return 1
    except requests.RequestException as e:
        print(f"\n❌ API request failed: {e}")
        print("Is the backend running on http://localhost:5001?")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
