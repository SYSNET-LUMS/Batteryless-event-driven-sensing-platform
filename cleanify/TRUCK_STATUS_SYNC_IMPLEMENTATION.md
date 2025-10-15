# Truck Status Synchronization Implementation

## Problem Solved
Truck status updates were scattered across multiple places and didn't consistently update the proactive dispatch service, leading to stale assignment tracking and phantom truck assignments.

## Solution: Centralized Status Updates

### Backend Changes

#### 1. `simulation_routes.py` - Centralized Truck State Updates
**File**: `cleanify/simulation-backend/src/api/routes/simulation_routes.py`

**Changes**:
- Modified `update_truck_simulation_state()` to accept an optional `agent` parameter
- Added cleanup call when trucks complete routes (status becomes 'available'):
  ```python
  if truck['status'] == 'returning' and distance_to_next <= 0:
      truck['status'] = 'available'
      # ... other cleanup ...
      
      # Cleanup: Update proactive dispatch tracking
      if agent:
          try:
              agent.update_truck_assignment_status(truck['id'], 'completed_route')
              print(f"🧹 Cleaned up assignments for truck {truck['id']}")
          except Exception as e:
              print(f"⚠️ Error cleaning up truck assignment: {e}")
  ```

- Updated the simulation step loop to pass `agent` and include 'returning' status:
  ```python
  for truck in trucks:
      if truck.get('status') in ['traveling', 'on_route', 'collecting', 'returning']:
          truck_updated = update_truck_simulation_state(truck, time_delta, repo, agent)
  ```

#### 2. `proactive_cluster_dispatch_service.py` - Enhanced Cleanup Logic
**File**: `cleanify/simulation-backend/src/services/proactive_cluster_dispatch_service.py`

**Changes**:
- Enhanced `update_truck_assignments()` to handle multiple status values:
  ```python
  if status in ['completed_route', 'available', 'idle']:
      # Remove completed/idle assignments to allow truck reassignment
      clusters_to_remove = []
      for cluster_id, assignment in self.active_cluster_assignments.items():
          if assignment['truck_id'] == truck_id:
              clusters_to_remove.append(cluster_id)
      
      for cluster_id in clusters_to_remove:
          del self.active_cluster_assignments[cluster_id]
          logger.info(f"🧹 Cleared assignment for truck {truck_id} - status: {status}")
  ```

### Frontend Changes

#### 3. `script.js` - Frontend Status Notifications
**File**: `cleanify/simulation-playground/script.js`

**Changes**:

1. **When truck returns to depot** (in `moveItemStraightLine`):
   ```javascript
   if (distance < 0.001) {
       if (target === truck.targetDepot) {
           truck.status = 'idle';
           truck.currentLoad = 0;
           truck.targetDepot = null;
           console.log(`🏭 ${truck.id} returned to depot and unloaded`);
           // Notify backend that truck completed its route
           updateTruckAssignmentStatus(truck.id, 'completed_route');
       }
   }
   ```

2. **Enhanced idle state handling** (in `updateTruck` switch case):
   ```javascript
   case 'idle':
       if (truck.currentLoad > 0) {
           // Return to depot
           truck.status = 'returning_to_depot';
           // ... depot routing ...
       } else {
           // Ensure backend knows truck is available
           if (!truck._idleNotified) {
               updateTruckAssignmentStatus(truck.id, 'available');
               truck._idleNotified = true;
           }
       }
       break;
   ```

3. **Existing status update** (already present in `handleRouteCompletion`):
   ```javascript
   if (routeType === 'return') {
       truck.status = 'idle';
       // ... other cleanup ...
       
       // Notify proactive dispatch that route is completed
       updateTruckAssignmentStatus(truck.id, 'route_completed');
   }
   ```

## Status Update Flow

### Truck Lifecycle Status Updates:

1. **Route Started**: 
   - Frontend calls `updateTruckAssignmentStatus(truck_id, 'route_started', assigned_bins)`
   - Backend tracks active assignment

2. **Route Completed**: 
   - Backend automatically detects when truck returns to depot (status → 'available')
   - Backend calls `agent.update_truck_assignment_status(truck_id, 'completed_route')`
   - Frontend also calls `updateTruckAssignmentStatus(truck_id, 'completed_route')` when route finishes
   - Proactive dispatch service removes stale assignments

3. **Truck Idle**: 
   - Frontend ensures backend is notified when truck is truly idle
   - Backend clears any phantom assignments

## API Endpoint Used

**Endpoint**: `/api/update_truck_assignment`
**Method**: POST
**Body**:
```json
{
  "truck_id": "Truck-1",
  "status": "completed_route" | "available" | "route_started",
  "assigned_bins": ["Bin-1", "Bin-2"],  // optional, for route_started
  "simulation_time": 25200
}
```

**Implementation** (already exists in `ai_routes.py`):
```python
@bp.route('/update_truck_assignment', methods=['POST'])
def update_truck_assignment():
    # Updates agent's proactive dispatch tracking
    agent.update_truck_assignment_status(truck_id, status)
```

## Benefits

1. **No Phantom Assignments**: Trucks are properly cleared from active assignments when routes complete
2. **Consistent State**: Backend and frontend stay synchronized about truck availability
3. **Proper Cluster Reassignment**: Completed clusters can be reassigned to other trucks
4. **Reduced Duplicate Dispatches**: The proactive dispatch system accurately tracks which trucks are busy
5. **Automatic Cleanup**: Both backend simulation loop and frontend UI trigger cleanup

## Testing

To verify the implementation works:

1. Start a simulation with multiple trucks and bins
2. Watch the proactive dispatch status endpoint: `/api/proactive_dispatch_status`
3. When trucks complete routes, verify:
   - `active_assignments` decreases
   - Trucks show as available in the system
   - New cluster assignments can be made to those trucks
4. Check console logs for:
   - `🧹 Cleaned up assignments for truck Truck-X`
   - `📋 Updated truck Truck-X status to completed_route`

## Future Improvements

1. Add periodic stale assignment cleanup (backend already has `clear_stale_assignments` method)
2. Add metrics/monitoring for assignment tracking accuracy
3. Consider adding WebSocket updates for real-time status sync
4. Add unit tests for assignment lifecycle
