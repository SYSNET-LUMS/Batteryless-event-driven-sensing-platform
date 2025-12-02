# Collection Lifecycle Fix

**Date:** December 2, 2025  
**Branch:** refactor-minimalist-v2

## Problems Fixed

### Issue 1: Missing Collection Endpoint
- **Problem:** Frontend calls `/api/bins_collected` but endpoint was missing
- **Impact:** Collected bins never reset, remained at fillLevel=100% forever
- **Solution:** Added `POST /api/bins_collected` endpoint

### Issue 2: The Capacity Bug
- **Problem:** When truck returns early (capacity full), unvisited bins remain `dispatched=True`
- **Impact:** Bins locked forever, never dispatched again, eventually overflow
- **Solution:** Added `POST /api/update_truck_status` with automatic bin release logic

### Issue 3: VROOM Capacity Constraints
- **Problem:** VROOM payload missing `capacity` and `delivery` fields
- **Impact:** VROOM couldn't enforce truck capacity limits
- **Solution:** Added integer-cast capacity/delivery to VROOM payload

---

## Changes Made

### 1. `src/api/routes/dispatch_routes.py`

#### New Endpoint: `POST /api/bins_collected`
```json
Request:  { "truck_id": "TRUCK_1", "collected_bin_ids": ["BIN_1", "BIN_2"] }
Response: { "status": "success", "updated_bins": 2, "truck_load_freed": 150 }
```

**Logic:**
- Find bins by ID in SystemRepository
- Reset `fillLevel = 0`
- Set `dispatched = False` (unlock for future dispatch)
- Set `assigned_truck = None`
- Update truck `current_load` (subtract collected weight)

#### New Endpoint: `POST /api/update_truck_status`
```json
Request:  { "truck_id": "TRUCK_1", "status": "idle" }
Response: { "status": "success", "released_bins": 1 }
```

**Logic:**
- Update truck status in repository
- **CRITICAL FIX:** If status becomes `'idle'`, scan all bins:
  - Find bins where `assigned_truck == truck_id` AND `dispatched == True`
  - Release them: `dispatched = False`, `assigned_truck = None`
  - Prevents capacity bug: unvisited bins are unlocked for next dispatch

---

### 2. `src/services/external/vroom_service.py`

**Added Capacity Constraints:**

```python
# Jobs now include delivery demand (bin fill level)
jobs.append({
    "id": int_id,
    "location": [bin_data['lng'], bin_data['lat']],
    "service": 300,
    "delivery": [int(bin_data.get('fillLevel', 0))]  # Integer required
})

# Vehicles now include capacity
vehicles.append({
    "id": int_id,
    "start": [depot['lng'], depot['lat']],
    "end": [depot['lng'], depot['lat']],
    "capacity": [int(truck.get('capacity', 100))],  # Integer required
    "profile": "car"
})
```

**Why:**
- VROOM strictly requires integers for capacity constraints
- Without this, VROOM would assign 10 bins to a truck with capacity=100 even if total fillLevel=1000

---

## Complete Lifecycle Flow

### 1. **Dispatch** (Working)
```
Frontend: POST /api/dispatch
Backend:  Filter bins → VROOM optimize → Update state
          trucks[].status = 'dispatching'
          bins[].dispatched = True
          bins[].assigned_truck = truck_id
```

### 2. **Collection** (Now Fixed)
```
Frontend: POST /api/bins_collected
Backend:  bins[].fillLevel = 0
          bins[].dispatched = False
          bins[].assigned_truck = None
          trucks[].current_load -= collected_weight
```

### 3. **Completion** (Now Fixed)
```
Frontend: POST /api/update_truck_status { status: 'idle' }
Backend:  trucks[].status = 'idle'
          IF idle: Release unvisited bins (dispatched=False)
```

---

## Testing Checklist

- [ ] Start backend: `python src/main.py`
- [ ] Dispatch trucks: Click "Dispatch" in frontend
- [ ] Collect bins: Truck visits bin → frontend calls `/api/bins_collected`
- [ ] Verify bin reset: Check bin `fillLevel=0`, `dispatched=False`
- [ ] Test capacity bug: Load truck with 3 bins, capacity only fits 2
  - Truck should return after 2 bins
  - Frontend calls `/api/update_truck_status` with `status='idle'`
  - Backend releases 3rd bin (dispatched=False)
  - Next dispatch cycle picks up 3rd bin

---

## Code Metrics

**dispatch_routes.py:**
- Added 2 endpoints: `bins_collected`, `update_truck_status`
- Added ~120 lines
- Critical fix: Bin release loop in `update_truck_status`

**vroom_service.py:**
- Modified `_build_vroom_payload()` to add `delivery` and `capacity`
- Added 2 lines with integer casting: `int(fillLevel)`, `int(capacity)`
