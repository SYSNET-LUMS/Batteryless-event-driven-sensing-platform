# Collection Queue Synchronization Implementation

## Problem Solved
The collection queue was rebuilt on every routing decision but was never exposed to the frontend during simulation steps, causing the UI to show outdated or incorrect queue information that didn't match the backend's actual routing decisions.

## Solution: Real-Time Queue Synchronization

### Backend Changes

#### 1. `simulation_routes.py` - Include Queue in Simulation Step Response
**File**: `cleanify/simulation-backend/src/api/routes/simulation_routes.py`

**Changes in `simulation_step()` function**:
```python
# Get current collection queue from agent
collection_queue_ids = []
if agent and hasattr(agent, 'collection_queue'):
    collection_queue_ids = list(agent.collection_queue)

return jsonify({
    "status": "success",
    "bins": repo.get_bins(),
    "bins_hit_threshold": bins_that_hit_threshold,
    "updated_urgencies": {},
    "traffic_info": traffic_info,
    "clusters": clusters_data,
    "reserved_bins": list(agent.reserved_bins) if agent else [],
    "waiting_assignments": len(agent.waiting_assignments) if agent else 0,
    "schedule_dispatches": schedule_dispatches,
    "collection_queue": collection_queue_ids,  # NEW: Include queue in response
    "message": f"Simulation step completed ({time_delta}s)"
})
```

**Impact**: Every simulation step now includes the current state of the backend's collection queue, ensuring the frontend has real-time access to the exact bins being prioritized for routing.

### Frontend Changes

#### 2. `script.js` - Store and Use Backend Queue
**File**: `cleanify/simulation-playground/script.js`

**Change 1: Store backend queue in `callBackendSimulationStep()`**:
```javascript
async function callBackendSimulationStep(timeDelta) {
    try {
        const response = await fetch(`${API_BASE}/simulation_step`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                time_delta: timeDelta,
                simulation_time: simulationTime
            })
        });

        const data = await response.json();
        if (data.status === 'success') {
            // ... existing bin and cluster updates ...

            // NEW: Store the backend collection queue for UI synchronization
            window.backendCollectionQueue = data.collection_queue || [];
            
            // NEW: Update the collection queue UI immediately with backend data
            updateCollectionQueueFromBackend();
        }
    } catch (error) {
        console.error('Backend simulation step failed:', error);
    }
}
```

**Change 2: New function to update queue from backend data**:
```javascript
// New function: Update collection queue using backend data from simulation step
function updateCollectionQueueFromBackend() {
    const container = document.getElementById('collectionQueue');
    
    // Use backend queue stored from simulation_step response
    const queueIds = window.backendCollectionQueue || [];
    
    if (queueIds.length === 0) {
        smoothUpdateQueueContainer(container, [], 'No collections needed');
        return;
    }
    
    // Map queue IDs to full bin objects
    const queueBins = queueIds
        .map(binId => items.bins.find(b => b.id === binId))
        .filter(bin => bin !== undefined);
    
    smoothUpdateQueueContainer(container, queueBins);
    previousQueue = [...queueBins];
}
```

**Change 3: Enhanced bin list with queue indicators**:
```javascript
function updateBinsList() {
    const container = document.getElementById('binsList');
    container.innerHTML = '';
    
    // Get backend collection queue for visual indicators
    const backendQueue = window.backendCollectionQueue || [];
    const queueSet = new Set(backendQueue);
    
    items.bins.forEach(bin => {
        const dynamicThreshold = bin.dynamic_threshold || bin.threshold || 80;
        const staticThreshold = bin.threshold || 80;
        const isTargeted = items.trucks.some(truck => truck.targetBin === bin);
        const inQueue = queueSet.has(bin.id);
        
        // Enhanced status with queue indicator
        let statusText = isTargeted ? 'TARGETED' :
            bin.fillLevel >= dynamicThreshold ? 'NEEDS COLLECTION' : 'OK';
        
        if (inQueue && !isTargeted) {
            statusText = '📋 IN QUEUE';
        }

        // ... rest of bin card creation ...
        
        let cardClass = `item-card ${getStatusClass(bin.fillLevel)}`;
        if (inQueue) {
            cardClass += ' in-queue';  // Add visual indicator class
        }
        card.className = cardClass;
        
        // ... rest of rendering ...
    });
}
```

#### 3. `style.css` - Visual Indicators for Queue Status
**File**: `cleanify/simulation-playground/style.css`

**New CSS classes**:
```css
.item-card {
    /* ... existing styles ... */
    position: relative;  /* Added for ::before positioning */
}

/* Visual indicator for bins in backend collection queue */
.item-card.in-queue {
    background: linear-gradient(90deg, #3498db22 0%, #34495e 20%);
    border-left-width: 6px;
    box-shadow: 0 0 8px rgba(52, 152, 219, 0.3);
}

.item-card.in-queue::before {
    content: '📋';
    position: absolute;
    right: 8px;
    top: 8px;
    font-size: 1.2rem;
    opacity: 0.7;
}
```

## Data Flow

### Synchronization Workflow:

1. **Simulation Step** (Backend):
   - Agent rebuilds collection queue based on bin priorities
   - Queue is included in `/api/simulation_step` response
   - Response: `{ ..., "collection_queue": ["Bin-1", "Bin-2", ...] }`

2. **Frontend Reception**:
   - `callBackendSimulationStep()` receives response
   - Stores queue in `window.backendCollectionQueue`
   - Immediately calls `updateCollectionQueueFromBackend()`

3. **UI Updates**:
   - Collection Queue panel: Shows exact bins from backend queue
   - Bins List: Adds `in-queue` class and 📋 indicator
   - Status text: Shows "📋 IN QUEUE" for queued bins

4. **Real-Time Sync**:
   - Every simulation step refreshes the queue
   - No separate API calls needed
   - UI always matches backend's routing decisions

## Visual Indicators

### Collection Queue Panel:
- Shows bins in priority order from backend
- Smooth animations when bins enter/exit queue
- "No collections needed" when queue is empty

### Bins List Panel:
- **Blue gradient background**: Bin is in collection queue
- **Thicker left border**: Enhanced visibility (6px vs 4px)
- **📋 Icon**: Top-right corner indicator
- **Status text**: Shows "📋 IN QUEUE"
- **Subtle glow**: Box shadow for emphasis

### Example Visual States:
```
Normal bin:     [Green border]  Bin-1 45.2%
                OK | T: 80% | Rate: 3.5L/h

Queued bin:     [Blue border 📋]  Bin-2 82.3%
                📋 IN QUEUE | DT: 75.5% | Rate: 4.2L/h

Targeted bin:   [Red border]  Bin-3 91.5%
                TARGETED | T: 80% | Rate: 5.1L/h
```

## Benefits

1. **Accurate UI State**: Frontend shows exact queue used by backend routing
2. **No Desync**: Queue updates with every simulation step automatically
3. **Reduced API Calls**: No need for separate `/api/collection_queue` endpoint calls
4. **Visual Clarity**: Users can see which bins are prioritized for collection
5. **Debug-Friendly**: Easy to verify routing decisions match UI state

## Testing

### Verification Steps:

1. **Start Simulation**:
   ```bash
   # Backend
   cd simulation-backend
   python src/main.py
   
   # Frontend
   # Open simulation-playground/index.html
   ```

2. **Check Queue Synchronization**:
   - Load a system with multiple bins
   - Let bins fill up past threshold
   - Observe Collection Queue panel
   - Verify bins shown match those being targeted by routing

3. **Verify Visual Indicators**:
   - Check Bins List for 📋 icons
   - Confirm blue gradient appears on queued bins
   - Verify status text shows "📋 IN QUEUE"

4. **Test Real-Time Updates**:
   - Watch as bins enter/exit queue during simulation
   - Verify smooth animations
   - Confirm queue clears when trucks collect bins

### Console Verification:
```javascript
// Check current backend queue
console.log('Backend Queue:', window.backendCollectionQueue);

// Compare with displayed bins
const queueBins = window.backendCollectionQueue.map(id => 
    items.bins.find(b => b.id === id)
);
console.log('Queue Bins:', queueBins.map(b => 
    `${b.id}: ${b.fillLevel.toFixed(1)}%`
));
```

### Expected Console Output:
```
Backend Queue: ["Bin-3", "Bin-7", "Bin-1"]
Queue Bins: ["Bin-3: 85.2%", "Bin-7: 82.1%", "Bin-1: 78.5%"]
```

## Legacy Support

The original `updateCollectionQueue()` function still exists as a fallback:
- Can be called manually if needed
- Uses `/api/collection_queue` endpoint
- Useful for debugging or manual refresh

## Future Enhancements

1. **WebSocket Integration**: Push queue updates instead of polling
2. **Queue History**: Track how queue changes over time
3. **Priority Visualization**: Show numeric priority scores
4. **Routing Preview**: Highlight planned routes on map
5. **Performance Metrics**: Track queue efficiency and response times

## API Changes Summary

### Modified Endpoint:
**POST `/api/simulation_step`**

**Response (Added field)**:
```json
{
  "status": "success",
  "bins": [...],
  "collection_queue": ["Bin-1", "Bin-2", "Bin-3"],  // NEW
  "clusters": {...},
  "traffic_info": {...},
  // ... other fields
}
```

### No Breaking Changes:
- All existing fields remain unchanged
- `collection_queue` is an additive feature
- Frontend gracefully handles missing field (empty array fallback)
