#!/usr/bin/env python3

import requests
import json
import time

BASE_URL = "http://localhost:5001/api"

def test_recurring_schedule():
    print("🧪 Testing Recurring Schedule System")
    print("=" * 50)
    
    # Step 1: Check server health
    print("1. Checking server health...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"   ✅ Server health: {response.json()}")
    except Exception as e:
        print(f"   ❌ Server not accessible: {e}")
        return
    
    # Step 2: Initialize system
    print("\n2. Initializing system...")
    response = requests.post(f"{BASE_URL}/initialize", json={})
    print(f"   ✅ Initialize: {response.json()}")
    
    # Step 3: Load test system
    print("\n3. Loading test system...")
    response = requests.get(f"{BASE_URL}/load_system/5_Bin_1_Truck.json")
    data = response.json()
    system_state = data.get('systemState', {})
    trucks = system_state.get('trucks', [])
    bins = system_state.get('bins', [])
    depots = system_state.get('depots', [])
    print(f"   ✅ Loaded JSON: {len(trucks)} trucks, {len(bins)} bins, {len(depots)} depots")
    
    # Sync with backend repository (like frontend does)
    print("   🔄 Syncing with backend repository...")
    
    # Add depots first
    for depot in depots:
        response = requests.post(f"{BASE_URL}/depot", json=depot)
        if response.status_code != 200:
            print(f"   ⚠️ Failed to add depot {depot['id']}: {response.text}")
    
    # Add bins
    for bin_item in bins:
        response = requests.post(f"{BASE_URL}/bin", json=bin_item)
        if response.status_code != 200:
            print(f"   ⚠️ Failed to add bin {bin_item['id']}: {response.text}")
    
    # Add trucks
    for truck in trucks:
        response = requests.post(f"{BASE_URL}/truck", json=truck)
        if response.status_code != 200:
            print(f"   ⚠️ Failed to add truck {truck['id']}: {response.text}")
    
    print(f"   ✅ Repository sync complete")
    
    if trucks:
        print(f"   📦 Truck: {trucks[0]['id']}")
    if bins:
        print(f"   🗑️ Bins: {[b['id'] for b in bins[:3]]}")
    if depots:
        print(f"   🏢 Depot: {depots[0]['id']}")
    
    # Step 4: Create daily recurring schedule
    print("\n4. Creating daily recurring schedule...")
    schedule_data = {
        "truck_id": "TRUCK_1",
        "area_name": "Daily Test Area",
        "scheduled_hour": 8,
        "scheduled_minute": 0,
        "target_bin_ids": ["BIN_1", "BIN_2", "BIN_3"],
        "depot_id": "DEPOT_1",
        "recurrence_type": "daily",
        "max_occurrences": 3
    }
    
    response = requests.post(f"{BASE_URL}/schedules", json=schedule_data)
    if response.status_code == 200:
        result = response.json()
        print(f"   ✅ Schedule created: {result['schedule']['id']}")
        schedule_id = result['schedule']['id']
        
        # Show schedule details
        schedule = result['schedule']
        print(f"   📅 Schedule: {schedule.get('recurrence_type', 'N/A')} at {schedule.get('scheduled_hour', 'N/A')}:{schedule.get('scheduled_minute', 'N/A'):02d}")
        print(f"   🔄 Max occurrences: {schedule.get('max_occurrences', 'unlimited')}")
        print(f"   ⏰ Next execution: {schedule.get('next_execution_time', 'N/A')}")
    else:
        print(f"   ❌ Failed to create schedule: {response.text}")
        return
    
    # Step 5: Check all schedules
    print("\n5. Checking all schedules...")
    response = requests.get(f"{BASE_URL}/schedules")
    schedules = response.json().get('schedules', [])
    print(f"   📋 Total schedules: {len(schedules)}")
    
    for i, sched in enumerate(schedules):
        print(f"   {i+1}. {sched['id']}: {sched.get('recurrence_type', 'once')} - {sched['status']}")
        print(f"      Executions: {sched.get('total_executions', 0)}/{sched.get('max_occurrences', '∞')}")
        print(f"      Recurrence: {sched.get('recurrence_type')} every {sched.get('recurrence_interval')} hours")
        print(f"      Next execution time: {sched.get('next_execution_time')}")
        print(f"      Scheduled time: {sched.get('scheduled_time')}")
        print(f"      Raw schedule data: {json.dumps(sched, indent=2)}")
        print("      ---")
    
    # Step 6: Test simulation step (to see if schedule gets processed)
    print("\n6. Testing simulation step to check schedule processing...")
    
    # First, start simulation
    response = requests.post(f"{BASE_URL}/start_simulation", json={})
    print(f"   🚀 Simulation start: {response.json()}")
    
    # Step simulation to time 3600 (8:00 AM, 1 hour into simulation)
    print("   ⏰ Stepping simulation to 8:00 AM (scheduled time)...")
    for step in range(1, 61):  # 60 steps of 1 minute each = 1 hour
        response = requests.post(f"{BASE_URL}/simulation_step", json={})
        result = response.json()
        simulation_time = result.get('systemState', {}).get('simulation', {}).get('time', 0)
        
        if step % 10 == 0:  # Print every 10th step
            print(f"   Step {step}: Simulation time = {simulation_time} seconds ({simulation_time/3600:.1f} hours)")
        
        # Check if any scheduled dispatches occurred
        if 'scheduled_dispatches' in result and result['scheduled_dispatches']:
            print(f"   🚛 Scheduled dispatch executed at time {simulation_time}!")
            print(f"      Dispatches: {result['scheduled_dispatches']}")
    
    # Step 7: Check schedule status after execution
    print("\n7. Checking schedule status after execution...")
    response = requests.get(f"{BASE_URL}/schedules")
    schedules = response.json().get('schedules', [])
    
    for sched in schedules:
        print(f"   {sched['id']}: {sched['status']}")
        print(f"   Executions: {sched.get('total_executions', 0)}/{sched.get('max_occurrences', '∞')}")
        print(f"   Next execution: {sched.get('next_execution_time', 'N/A')}")
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    test_recurring_schedule()