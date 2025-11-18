# Truck Dispatching Logic

## Overview
The truck dispatching system determines when, where, and how to send trucks for waste collection. The current implementation uses a **simplified cluster-scoped single-truck dispatch** strategy with traffic awareness and fuel efficiency optimization.

## Primary Service
**File**: `cleanify/simulation-backend/src/services/proactive_cluster_dispatch_service.py`  
**Class**: `ProactiveClusterDispatchService`  
**Main Method**: `process_bin_reached_dt()`

---

## Dispatch Strategy

### Core Principles
1. ✅ **Cluster-Scoped Collection**: When one bin reaches threshold, collect entire cluster
2. ✅ **Single-Truck per Cluster**: Only one truck assigned per cluster at a time
3. ✅ **Traffic Awareness**: Wait for better traffic conditions if safe
4. ✅ **Fuel Efficiency**: Maximize bins collected per trip within capacity
5. ✅ **No Duplicate Dispatches**: Active cluster assignments prevent redundant trucks

---

## Step-by-Step Dispatch Flow

### Phase 1: Trigger Detection

#### Entry Point
```python
def process_bin_reached_dt(
    trigger_bin,           # Bin that reached dynamic threshold
    all_bins,              # All system bins
    trucks,                # Available trucks
    current_time,          # Simulation time (seconds)
    existing_collection_queue  # Bins already queued
):
```

#### Trigger Condition
```python
if trigger_bin['fillLevel'] >= trigger_bin['dynamicThreshold']:
    # Bin needs collection - start dispatch logic
```

**Example**: BIN_1 at 85% fill, threshold 80% → Triggers dispatch

---

### Phase 2: Cluster Lookup

#### Find Cluster for Trigger Bin
```python
# Get clustering service
clustering = ClusteringService()
clusters = clustering.cluster_bins_by_proximity(all_bins, depots)

# Find which cluster contains trigger bin
trigger_cluster = None
for cluster in clusters:
    if any(b['id'] == trigger_bin['id'] for b in cluster['bins']):
        trigger_cluster = cluster
        break
```

#### Check for Existing Assignment
```python
cluster_id = trigger_cluster['cluster_id']

if cluster_id in self.active_cluster_assignments:
    return {
        'dispatch_recommendation': 'wait_for_existing_truck',
        'reason': 'Cluster already assigned to a truck',
        'existing_truck_id': self.active_cluster_assignments[cluster_id]['truck_id']
    }
```

**Purpose**: Prevent duplicate trucks dispatching to same cluster.

---

### Phase 3: Build Candidate Bin Set

#### Eligibility Criteria
```python
candidate_bins = []
for bin in trigger_cluster['bins']:
    # Include if:
    # 1. Not already in collection queue
    # 2. Fill level > 50% of threshold (avoid near-empty bins)
    # 3. Has current fill level data
    
    if (bin['id'] not in existing_queue_ids and
        bin['fillLevel'] >= bin['dynamicThreshold'] * 0.5 and
        bin.get('currentFill', 0) > 0):
        candidate_bins.append(bin)
```

**Threshold Multiplier**: 0.5 means collect bins at ≥50% of their dynamic threshold.

**Example**:
```
BIN_1: 85% fill, 80% threshold → 85 >= 80*0.5 = 40 ✓ INCLUDE
BIN_2: 60% fill, 80% threshold → 60 >= 80*0.5 = 40 ✓ INCLUDE
BIN_3: 30% fill, 80% threshold → 30 >= 80*0.5 = 40 ✗ EXCLUDE
BIN_4: 70% fill, 90% threshold → 70 >= 90*0.5 = 45 ✓ INCLUDE
```

---

### Phase 4: Score and Rank Candidates

#### Scoring Formula
```python
def _compute_bin_score(bin, truck_location):
    # Normalized components (0-1 scale)
    fill_score = bin['fillLevel'] / 100.0
    fill_rate_score = min(bin.get('fillRate', 0) / 10.0, 1.0)
    
    # Proximity score (closer = higher score)
    distance_km = calculate_distance_km(truck_location, bin)
    proximity_score = 1.0 / (1.0 + distance_km)
    
    # Weighted combination
    score = (
        0.55 * fill_score +      # 55% weight on current fill
        0.30 * fill_rate_score + # 30% weight on urgency (fill rate)
        0.15 * proximity_score   # 15% weight on distance
    )
    
    return score
```

#### Greedy Selection per Truck
```python
for truck in available_trucks:
    selected_bins = []
    remaining_capacity = truck['capacity'] * 0.95  # 5% safety margin
    
    # Sort candidates by score (highest first)
    sorted_candidates = sorted(
        candidate_bins,
        key=lambda b: _compute_bin_score(b, truck['location']),
        reverse=True
    )
    
    # Greedily select bins until capacity reached
    for bin in sorted_candidates:
        if bin['currentFill'] <= remaining_capacity:
            selected_bins.append(bin)
            remaining_capacity -= bin['currentFill']
        
        if remaining_capacity < 50:  # Stop if < 50L capacity left
            break
    
    truck['proposed_bins'] = selected_bins
    truck['proposed_load'] = sum(b['currentFill'] for b in selected_bins)
```

**Scoring Weights**:
- **55% Fill Level**: Prioritize fuller bins (overflow prevention)
- **30% Fill Rate**: Prioritize fast-filling bins (urgency)
- **15% Proximity**: Slight preference for nearby bins (fuel efficiency)

---

### Phase 5: Select Best Truck

#### Selection Criteria
```python
best_truck = max(
    [t for t in trucks if len(t['proposed_bins']) > 0],
    key=lambda t: len(t['proposed_bins'])  # Most bins wins
)
```

**Rationale**: Maximize bins per trip for fuel efficiency.

**Tie-breaker** (implicit): If multiple trucks can collect same number of bins, first available truck selected.

---

### Phase 6: Traffic-Aware Dispatch Decision

#### Traffic Manager Integration
```python
from services.traffic_service import TrafficManager

traffic_mgr = TrafficManager()

dispatch_decision = traffic_mgr.calculate_dispatch_time(
    bin_data=trigger_bin,
    current_time=current_time,
    travel_time_base=estimated_travel_time  # Without traffic
)
```

#### Decision Logic (TrafficManager)
```python
def calculate_dispatch_time(bin_data, current_time, travel_time_base):
    # 1. Check overflow risk
    time_to_overflow = (bin_data['capacity'] - bin_data['fillLevel']) / bin_data['fillRate']
    
    if time_to_overflow < 2.0:  # Less than 2 hours
        return {
            'action': 'dispatch_now',
            'reason': 'Critical overflow risk'
        }
    
    # 2. Get current and predicted traffic
    current_density = get_traffic_density(current_time)
    
    if current_density < 5.0:  # Light/moderate traffic
        return {
            'action': 'dispatch_now',
            'reason': f'Favorable traffic (density: {current_density})'
        }
    
    # 3. Heavy traffic - check if waiting is safe
    next_window = find_optimal_dispatch_around_heavy_traffic(
        current_time,
        time_to_overflow,
        travel_time_base
    )
    
    if next_window['recommended_action'] == 'wait':
        return {
            'action': 'wait',
            'wait_min': next_window['wait_minutes'],
            'reason': f'Wait for lighter traffic (saves {next_window["time_saved"]:.1f} min)'
        }
    else:
        return {
            'action': 'dispatch_now',
            'reason': 'Dispatch now safer than waiting'
        }
```

**Traffic Density Scale**:
```python
traffic_density = {
    0: 1.5,   # 12 AM - Light
    1: 1.2,
    # ...
    7: 8.0,   # 7 AM - Heavy (pre-rush)
    8: 10.0,  # 8 AM - Very heavy (morning rush)
    9: 8.5,
    # ...
    17: 10.0, # 5 PM - Very heavy (evening rush)
    18: 8.0,
    # ...
    23: 2.0
}
```

**Thresholds**:
- **< 3.0**: Light traffic
- **3.0 - 5.0**: Moderate traffic
- **> 5.0**: Heavy traffic

---

### Phase 7: Route Computation

#### Nearest-Neighbor TSP Heuristic
```python
def _compute_nearest_neighbor_route(truck, selected_bins):
    route = []
    current_location = truck['location']
    remaining_bins = selected_bins.copy()
    
    while remaining_bins:
        # Find nearest unvisited bin
        nearest = min(
            remaining_bins,
            key=lambda b: calculate_distance_km(current_location, b)
        )
        
        route.append(nearest['id'])
        current_location = nearest
        remaining_bins.remove(nearest)
    
    return route
```

**Algorithm**: Simple greedy nearest-neighbor
- **Time Complexity**: O(n²) where n = selected bins
- **Quality**: Typically within 25% of optimal for small n (<10)
- **Speed**: Fast enough for real-time dispatch

**Example Route**:
```
Truck at DEPOT_1 (33.6000, 73.0800)
Selected bins: [BIN_1, BIN_2, BIN_3, BIN_4]

Step 1: Nearest to DEPOT → BIN_4 (874m)
Step 2: Nearest to BIN_4 → BIN_1 (932m)
Step 3: Nearest to BIN_1 → BIN_2 (95m)
Step 4: Nearest to BIN_2 → BIN_3 (60m)

Final route: [BIN_4, BIN_1, BIN_2, BIN_3]
```

---

### Phase 8: Register Cluster Assignment

#### Create Assignment Record
```python
cluster_id = trigger_cluster['cluster_id']
selected_bin_ids = [b['id'] for b in selected_bins]

self.active_cluster_assignments[cluster_id] = {
    'truck_id': best_truck['id'],
    'assigned_bins': selected_bin_ids,
    'total_load': sum(b['currentFill'] for b in selected_bins),
    'timestamp': current_time,
    'route': computed_route
}
```

**Purpose**: Block future dispatches to this cluster until truck completes collection.

---

### Phase 9: Return Dispatch Result

#### Result Format
```python
return {
    'dispatch_recommendation': 'dispatch' | 'wait',
    'assigned_truck_id': best_truck['id'],
    'additional_bins_for_queue': [other_bin_ids_in_route],
    'route': [bin_id_1, bin_id_2, bin_id_3, ...],
    'estimated_capacity_after': truck['capacity'] - total_load,
    'reason': 'Proactive cluster dispatch simplified: assigned N bins',
    'wait_min': optional_wait_minutes  # If wait recommendation
}
```

---

## Complete Example Walkthrough

### Input State
```json
{
  "trigger_bin": {
    "id": "BIN_1",
    "fillLevel": 85,
    "dynamicThreshold": 80,
    "fillRate": 5.0,
    "currentFill": 200,
    "capacity": 500,
    "lat": 33.6092,
    "lng": 73.0825
  },
  "trucks": [
    {
      "id": "TRUCK_1",
      "capacity": 2000,
      "currentLoad": 300,
      "status": "returning",
      "location": {"lat": 33.6050, "lng": 73.0850}
    },
    {
      "id": "TRUCK_2",
      "capacity": 2000,
      "currentLoad": 0,
      "status": "available",
      "location": {"lat": 33.6000, "lng": 73.0800}
    }
  ],
  "current_time": 7200,
  "other_cluster_bins": [
    {"id": "BIN_2", "fillLevel": 60, "threshold": 80, "currentFill": 150, ...},
    {"id": "BIN_3", "fillLevel": 70, "threshold": 90, "currentFill": 180, ...},
    {"id": "BIN_4", "fillLevel": 55, "threshold": 75, "currentFill": 120, ...}
  ]
}
```

### Step-by-Step Execution

#### 1. Cluster Lookup
```
Cluster 0: [BIN_1, BIN_2, BIN_3, BIN_4]
No active assignment for Cluster 0 ✓
```

#### 2. Build Candidates
```
BIN_1: 85 >= 80*0.5 = 40 ✓ currentFill: 200L
BIN_2: 60 >= 80*0.5 = 40 ✓ currentFill: 150L
BIN_3: 70 >= 90*0.5 = 45 ✓ currentFill: 180L
BIN_4: 55 >= 75*0.5 = 37.5 ✓ currentFill: 120L

Candidates: [BIN_1, BIN_2, BIN_3, BIN_4]
```

#### 3. Score Candidates (TRUCK_2 perspective)
```
BIN_1: score = 0.55*0.85 + 0.30*(5/10) + 0.15*proximity = 0.77
BIN_2: score = 0.55*0.60 + 0.30*(3/10) + 0.15*proximity = 0.51
BIN_3: score = 0.55*0.70 + 0.30*(4/10) + 0.15*proximity = 0.62
BIN_4: score = 0.55*0.55 + 0.30*(2/10) + 0.15*proximity = 0.45

Sorted: [BIN_1, BIN_3, BIN_2, BIN_4]
```

#### 4. Greedy Selection (TRUCK_2: 2000L capacity, 5% safety = 1900L usable)
```
Select BIN_1: 200L → Remaining: 1700L ✓
Select BIN_3: 180L → Remaining: 1520L ✓
Select BIN_2: 150L → Remaining: 1370L ✓
Select BIN_4: 120L → Remaining: 1250L ✓

TRUCK_2 proposal: [BIN_1, BIN_3, BIN_2, BIN_4], load: 650L
```

#### 5. Select Best Truck
```
TRUCK_1: Not available (status: returning)
TRUCK_2: 4 bins, 650L load

Winner: TRUCK_2
```

#### 6. Traffic Check (current_time = 7200s = 2:00 AM)
```
Traffic density at 2:00 AM: 1.2 (light)
Overflow risk: (500-200)/5.0 = 60 hours (safe)

Decision: DISPATCH_NOW
Reason: "Favorable traffic (density: 1.2)"
```

#### 7. Compute Route (Nearest-Neighbor from DEPOT location)
```
Start: DEPOT (33.6000, 73.0800)

Nearest to DEPOT: BIN_4 (distance: 874m)
Nearest to BIN_4: BIN_1 (distance: 932m)
Nearest to BIN_1: BIN_2 (distance: 95m)
Nearest to BIN_2: BIN_3 (distance: 60m)

Route: [BIN_4, BIN_1, BIN_2, BIN_3]
```

#### 8. Register Assignment
```python
active_cluster_assignments[0] = {
    'truck_id': 'TRUCK_2',
    'assigned_bins': ['BIN_1', 'BIN_3', 'BIN_2', 'BIN_4'],
    'total_load': 650.0,
    'timestamp': 7200,
    'route': ['BIN_4', 'BIN_1', 'BIN_2', 'BIN_3']
}
```

#### 9. Return Result
```json
{
  "dispatch_recommendation": "dispatch",
  "assigned_truck_id": "TRUCK_2",
  "additional_bins_for_queue": ["BIN_3", "BIN_2", "BIN_4"],
  "route": ["BIN_4", "BIN_1", "BIN_2", "BIN_3"],
  "estimated_capacity_after": 1350,
  "reason": "Proactive cluster dispatch simplified: assigned 4 bins"
}
```

---

## Assignment Lifecycle Management

### 1. Update Truck Position
```python
def update_truck_assignments(truck_id, new_location):
    # Update truck location in active assignments
    for cluster_id, assignment in active_cluster_assignments.items():
        if assignment['truck_id'] == truck_id:
            assignment['last_location'] = new_location
```

### 2. Mark Bins Collected
```python
def mark_bins_collected(truck_id, collected_bin_ids):
    # Remove collected bins from assignment
    for cluster_id, assignment in active_cluster_assignments.items():
        if assignment['truck_id'] == truck_id:
            assignment['assigned_bins'] = [
                b for b in assignment['assigned_bins']
                if b not in collected_bin_ids
            ]
            
            # If all bins collected, clear assignment
            if not assignment['assigned_bins']:
                del active_cluster_assignments[cluster_id]
```

### 3. Clear Stale Assignments
```python
def clear_stale_assignments(current_time, timeout_seconds=3600):
    # Remove assignments older than 1 hour
    to_remove = []
    for cluster_id, assignment in active_cluster_assignments.items():
        if current_time - assignment['timestamp'] > timeout_seconds:
            to_remove.append(cluster_id)
    
    for cluster_id in to_remove:
        del active_cluster_assignments[cluster_id]
```

---

## Traffic Prediction Logic

### Predictive Dispatch Around Heavy Traffic

#### Scenario: Current time in heavy traffic window
```python
def find_optimal_dispatch_around_heavy_traffic(
    current_time,
    time_to_overflow,
    travel_time_base
):
    # Find next light traffic window
    for future_hour in range(current_hour + 1, current_hour + 12):
        if traffic_density[future_hour % 24] < 3.0:
            wait_time = (future_hour - current_hour) * 3600
            
            # Check if safe to wait
            if wait_time + travel_time_base < time_to_overflow:
                # Calculate time saved
                current_trip_time = travel_time_base * traffic_density[current_hour]
                future_trip_time = travel_time_base * traffic_density[future_hour % 24]
                time_saved = current_trip_time - future_trip_time - wait_time
                
                if time_saved > 0:
                    return {
                        'recommended_action': 'wait',
                        'wait_minutes': wait_time / 60,
                        'time_saved': time_saved / 60,
                        'dispatch_hour': future_hour % 24
                    }
    
    return {'recommended_action': 'dispatch_now'}
```

#### Example
```
Current: 8:00 AM (density: 10.0, heavy traffic)
Travel time base: 20 minutes
Time to overflow: 5 hours

Check 9:00 AM: density 8.5 (still heavy)
Check 10:00 AM: density 6.0 (still heavy)
Check 11:00 AM: density 2.5 (light) ✓

Wait time: 3 hours
Current trip: 20 * 10.0 = 200 minutes
Future trip: 20 * 2.5 = 50 minutes
Time saved: 200 - 50 - 180 = -30 minutes (negative - don't wait)

Result: DISPATCH_NOW
```

---

## Configuration Parameters

### Scoring Weights
```python
SCORE_WEIGHTS = {
    'fill': 0.55,      # Current fill level weight
    'fill_rate': 0.30, # Fill rate (urgency) weight
    'proximity': 0.15  # Distance weight
}
```

### Capacity Safety Margin
```python
CAPACITY_SAFETY_MARGIN = 0.95  # Use 95% of truck capacity
```

### Candidate Threshold Multiplier
```python
CANDIDATE_THRESHOLD_MULT = 0.5  # Collect bins >= 50% of their threshold
```

### Traffic Thresholds
```python
LIGHT_TRAFFIC_THRESHOLD = 3.0
MODERATE_TRAFFIC_THRESHOLD = 5.0
# Above 5.0 = Heavy traffic
```

### Overflow Risk Threshold
```python
CRITICAL_OVERFLOW_HOURS = 2.0  # Dispatch immediately if < 2 hours to overflow
```

---

## Edge Cases Handled

### 1. No Available Trucks
```python
if not available_trucks:
    return {
        'dispatch_recommendation': 'wait',
        'reason': 'No trucks available'
    }
```

### 2. All Bins Below Threshold
```python
if not candidate_bins:
    return {
        'dispatch_recommendation': 'wait',
        'reason': 'No bins in cluster meet collection criteria'
    }
```

### 3. Cluster Already Assigned
```python
if cluster_id in active_cluster_assignments:
    return {
        'dispatch_recommendation': 'wait_for_existing_truck',
        'reason': 'Cluster already assigned to a truck'
    }
```

### 4. Truck Capacity Exceeded
```python
# During greedy selection, stop if next bin won't fit
if bin['currentFill'] > remaining_capacity:
    continue  # Skip this bin
```

### 5. Critical Overflow Risk
```python
# Override traffic wait decision if overflow imminent
if time_to_overflow < CRITICAL_OVERFLOW_HOURS:
    return {'action': 'dispatch_now', 'reason': 'Critical overflow risk'}
```

---

## Performance Characteristics

### Time Complexity
- **Cluster lookup**: O(c) where c = number of clusters
- **Candidate filtering**: O(n) where n = bins in cluster
- **Scoring**: O(n × m) where m = available trucks
- **Greedy selection**: O(n × m)
- **TSP route**: O(k²) where k = selected bins
- **Overall**: **O(n × m + k²)** ≈ **O(nm)** for typical cases

### Space Complexity
- **Active assignments**: O(c)
- **Candidate storage**: O(n)
- **Overall**: **O(n + c)**

### Typical Values
- Bins per cluster: 3-10
- Available trucks: 1-5
- Selected bins: 3-8
- **Execution time**: < 10ms for typical scenarios

---

## Testing & Validation

### Test Results (Real System)
```
✅ System: cleanify_system_20251007_130200.json
   - Bins: 10, Trucks: 2, Depots: 1

✅ Dispatch Test:
   - Trigger: BIN_1 at 85% (threshold: 80%)
   - Cluster: 4 bins total
   - Assigned: TRUCK_2
   - Bins queued: 4 (BIN_1, BIN_3, BIN_2, BIN_4)
   - Route: [BIN_4, BIN_1, BIN_2, BIN_3]
   - Load: 650L / 2000L capacity
   - Decision: dispatch (favorable traffic)

✅ Duplicate Prevention:
   - Second dispatch attempt: wait_for_existing_truck
   - Reason: "Cluster already assigned to a truck"
```

### Validation Criteria
1. ✅ Only one truck per cluster at any time
2. ✅ All selected bins fit within truck capacity
3. ✅ Route visits all selected bins
4. ✅ Traffic considerations applied correctly
5. ✅ Overflow risk handled appropriately

---

## Integration with Other Services

### 1. ClusteringService
```python
# Get clusters for proximity-based dispatch
clusters = ClusteringService().cluster_bins_by_proximity(bins, depots)
```

### 2. TrafficManager
```python
# Get traffic-aware dispatch timing
decision = TrafficManager().calculate_dispatch_time(bin, time, travel_time)
```

### 3. SimulationService
```python
# Main simulation loop calls dispatch service
if bin['fillLevel'] >= bin['dynamicThreshold']:
    result = ProactiveClusterDispatchService().process_bin_reached_dt(...)
```

### 4. AgentManager (AI Agent)
```python
# Agent uses dispatch result to create tasks
if result['dispatch_recommendation'] == 'dispatch':
    agent.create_collection_task(
        truck_id=result['assigned_truck_id'],
        route=result['route']
    )
```

---

## Design Rationale

### Why Cluster-Scoped?
- **Fuel Efficiency**: Collect multiple nearby bins in one trip
- **Coordination**: Prevents multiple trucks in same area
- **Simplicity**: Clear boundaries for dispatch decisions

### Why Single-Truck per Cluster?
- **No Confusion**: Deterministic assignment, no conflicts
- **Predictable**: Frontend/agent knows exactly which truck serves which bins
- **Efficient**: Avoids underutilized trucks making partial trips

### Why Traffic Integration?
- **User Requirement**: Minimize truck interaction with heavy traffic
- **Time Savings**: Waiting for better traffic can reduce total trip time
- **Safety**: Overflow prevention overrides traffic wait decisions

### Why Greedy Selection?
- **Speed**: O(nm) fast enough for real-time
- **Quality**: Near-optimal for small bin counts (<10)
- **Simplicity**: Easy to understand and debug
- **Capacity-Aware**: Naturally respects truck limits

---

## Future Enhancements

### Potential Improvements
1. **Multi-Truck Coordination**: Allow multiple trucks if cluster very large
2. **Priority Levels**: High-priority bins override greedy selection
3. **Dynamic Re-routing**: Update route as bins fill during collection
4. **Historical Learning**: Adjust scoring weights based on past efficiency
5. **Predictive Fill Levels**: Estimate future fill at dispatch time
6. **Energy Optimization**: Consider electric truck range/charging
7. **Real-Time Traffic**: Integrate live traffic data APIs

---

## Comparison with Previous Complex System

### Old System (Before Simplification)
- ❌ Multiple dispatch paths (Decision, Optimization, DynamicRouteOptimizer, Proactive, Enhanced, Schedule)
- ❌ VROOM integration for route optimization (complex, slow)
- ❌ No clear cluster-level locking
- ❌ Duplicate dispatch risk
- ❌ Traffic scattered across services

### New System (Simplified)
- ✅ Single dispatch service (ProactiveClusterDispatchService)
- ✅ Simple nearest-neighbor TSP (fast, sufficient)
- ✅ Cluster-level assignment tracking
- ✅ Duplicate prevention guaranteed
- ✅ Centralized traffic management (TrafficManager)

---

## Summary

The truck dispatching system is a **cluster-scoped, traffic-aware, single-truck dispatch strategy** that:
- ✅ Triggers on bins reaching dynamic threshold
- ✅ Collects entire cluster in one trip (fuel efficient)
- ✅ Prevents duplicate dispatches via active assignment tracking
- ✅ Scores bins by fill level (55%), fill rate (30%), proximity (15%)
- ✅ Greedily selects bins to maximize capacity utilization
- ✅ Integrates traffic predictions to minimize heavy-traffic interaction
- ✅ Computes nearest-neighbor routes for efficient travel
- ✅ Handles edge cases (overflow risk, no trucks, capacity limits)

**Key Insight**: The dispatch system balances three competing objectives:
1. **Overflow Prevention**: Collect bins before they overflow
2. **Fuel Efficiency**: Maximize bins per trip, minimize distance
3. **Traffic Avoidance**: Wait for better traffic when safe

The simplified architecture eliminates confusion and ensures deterministic, predictable truck assignments.
