# Cleanify Backend v2.0 - Minimalist Architecture

## 🎯 Overview

Cleanify v2.0 is a streamlined waste collection simulation system powered by traffic-aware dispatch logic and VROOM route optimization. All legacy agent-based patterns, clustering services, and manual knapsack algorithms have been removed in favor of a simple, linear pipeline.

---

## 🏗️ Architecture

### Core Philosophy
- **Functional & Service-based**: No stateful "Agent" objects
- **Linear Pipeline**: API Request → Traffic Filter → VROOM Optimizer → Return Routes
- **Simple Persistence**: JSON file saving/loading

### Core Services

#### 1. **TrafficService** (`services/traffic_service.py`)
Pre-filters bins based on traffic conditions:
- **Input**: List of all bins above threshold
- **Logic**:
  - Determines if current hour is "Heavy Traffic" (8, 9, 17, 18)
  - For each bin:
    - Calculates `Time_To_Overflow = Remaining_Capacity / Fill_Rate`
    - Calculates `Time_To_Light_Traffic` (hours until traffic clears)
    - **Decision**: If heavy traffic AND overflow time > light traffic time + 1hr buffer → **WAIT**
    - Otherwise → **DISPATCH NOW**
- **Output**: `(bins_to_dispatch, bins_to_wait)`

#### 2. **VROOMService** (`services/external/vroom_service.py`)
Optimizes truck-to-bin assignments:
- **Input**: Filtered bins, available trucks, depot location
- **Process**: Converts to VROOM JSON format, posts to VROOM API
- **Output**: Optimized routes with bin sequences per truck
- **Fallback**: Simple one-bin-per-truck if VROOM unavailable

#### 3. **RoutingService** (`services/routing_service.py`)
Generates waypoints via OSRM for navigation.

#### 4. **SimulationService** (`services/simulation/simulation_service.py`)
Updates bin fill levels and handles time progression.

---

## 📡 API Endpoints

### Core Dispatch Endpoint

#### `POST /api/dispatch`
Main dispatch logic with traffic awareness.

**Request:**
```json
{
  "simulation_time": 3600
}
```

**Response:**
```json
{
  "status": "success",
  "routes": [
    {
      "truck_id": "TRUCK_1",
      "bin_ids": ["BIN_1", "BIN_2", "BIN_3"],
      "distance": 5000,
      "duration": 600
    }
  ],
  "waiting": ["BIN_4"],
  "traffic_filtered": 1,
  "dispatch_count": 1
}
```

**Logic Flow:**
1. Get all bins with `fillLevel >= threshold`
2. Pass to `TrafficService.filter_bins_for_dispatch()`
3. Dispatch bins → `VROOMService.optimize_routes()`
4. Waiting bins → Return to frontend for display
5. Frontend draws VROOM routes immediately

---

### Simulation Endpoints

#### `POST /api/start_simulation`
Initialize simulation state.

**Response:**
```json
{
  "status": "success",
  "message": "Simulation ready"
}
```

#### `POST /api/simulation_step`
Update bin fill levels only (no agents, no complex logic).

**Request:**
```json
{
  "time_delta": 60
}
```

**Response:**
```json
{
  "status": "success",
  "bins": [...],
  "message": "Simulation step completed (60s)"
}
```

#### `POST /api/route`
Get OSRM route between two points.

---

## 🚀 Setup & Running

### Prerequisites
```bash
# Install Python dependencies
pip install -r requirements.txt

# Start OSRM (Docker)
docker run -t -i -p 5000:5000 osrm/osrm-backend osrm-routed --algorithm mld /data/pakistan-latest.osrm

# Start VROOM (Docker)
docker run -t -i -p 3000:3000 vroomvrp/vroom
```

### Environment Configuration
Create `.env` file in `simulation-backend/`:

```env
# Server
HOST=0.0.0.0
PORT=5001

# External Services
OSRM_URL=http://localhost:5000
VROOM_URL=http://localhost:3000

# Traffic Configuration
TRAFFIC_HEAVY_HOURS=8,9,17,18
TRAFFIC_MULTIPLIER=1.5
TRAFFIC_BUFFER_HOURS=1.0

# Simulation
SIMULATION_START_HOUR=7
```

### Start Backend
```bash
cd cleanify/simulation-backend
python src/main.py
```

Backend will start on `http://localhost:5001`

### Start Frontend
```bash
cd cleanify/simulation-playground
# Open index.html in browser or use live server
```

---

## 🧪 Testing

Run the minimalist test suite:

```bash
cd cleanify/simulation-backend
python test_minimalist.py
```

**Tests cover:**
1. System initialization (bins, trucks, depot)
2. Traffic filtering during heavy hours
3. Dispatch during light traffic
4. VROOM integration
5. Simulation time progression
6. Configuration loading

---

## 📊 Configuration Options

### Traffic Settings
- `TRAFFIC_HEAVY_HOURS`: Comma-separated hours (0-23) with heavy traffic
- `TRAFFIC_MULTIPLIER`: Route time multiplier during heavy traffic (default: 1.5)
- `TRAFFIC_BUFFER_HOURS`: Safety buffer for overflow calculations (default: 1.0)

### VROOM Settings
- `VROOM_URL`: VROOM service endpoint
- `VROOM_TIMEOUT`: Request timeout in seconds (default: 10)

---

## 🗑️ Removed Components

The following legacy services were deleted:

### Deleted Services
- `clustering_service.py` (k-means clustering)
- `agent_service.py` (stateful agents)
- `agent_manager.py` (agent lifecycle)
- `dispatch_planner_service.py` (manual heuristics)
- `distance_cache_service.py` (distance caching)
- `routing/optimization_service.py` (manual knapsack)
- `routing/dynamic_route_optimizer.py`
- `routing/enhanced_truck_availability_service.py`
- `traffic/` (entire directory - legacy prediction)
- `simulation/decision_service.py`

### Total Code Reduction
- **~2000 lines** of legacy code removed
- **~500 lines** of new streamlined code added
- **Net reduction: ~1500 lines** (60% less code)

---

## 🔄 Migration from v1.0

### Breaking Changes
1. `/api/ai_decision/truck_routing` → `/api/dispatch`
2. No more agent polling or proactive dispatch
3. Response format changed (see API docs above)
4. Traffic logic moved to backend (no frontend traffic simulation)

### Frontend Updates Required
```javascript
// OLD
fetch(`${API_BASE}/ai_decision/truck_routing`)

// NEW
fetch(`${API_BASE}/dispatch`)
```

---

## 📈 Performance

### Before (v1.0)
- Complex agent state management
- Multiple clustering iterations
- Manual knapsack optimization
- ~200ms average dispatch time

### After (v2.0)
- Stateless traffic filtering
- Single VROOM API call
- Linear pipeline
- ~50ms average dispatch time (excluding VROOM)

---

## 🐛 Troubleshooting

### VROOM Not Available
System automatically falls back to simple one-bin-per-truck assignment.

Check VROOM status:
```bash
curl http://localhost:3000/health
```

### OSRM Not Available
Routes will fail. Ensure OSRM is running:
```bash
curl http://localhost:5000/health
```

### No Routes Generated
1. Check if bins are above threshold (default 80%)
2. Verify trucks are in 'idle' status
3. Check depot is configured
4. Review traffic filtering logic (bins may be waiting)

---

## 📝 Development

### Adding New Features
1. Services go in `src/services/`
2. Routes go in `src/api/routes/`
3. Models go in `src/models/`
4. Register new routes in `src/api/app.py`

### Code Style
- **Keep it simple**: No over-engineering
- **Functional**: Prefer functions over classes
- **Type hints**: Use Python type hints
- **Documentation**: Docstrings for all public methods

---

## 📄 License

MIT License - See LICENSE file for details.

---

## 👥 Contributors

- Original Cleanify team
- Minimalist refactor: 2025

---

## 🔗 Related Documentation

- [VROOM Documentation](https://github.com/VROOM-Project/vroom)
- [OSRM Documentation](http://project-osrm.org/)
- [Flask Documentation](https://flask.palletsprojects.com/)
