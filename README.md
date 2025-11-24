# Cleanify - Smart Waste Collection System

AI-powered waste collection system with distance-based routing, urgency scoring, and real-time simulation.

## Project Structure

```
Cleanify/
├── cleanify/
│   ├── simulation-backend/     # Flask backend API
│   │   └── src/               # Python source code
│   ├── simulation-playground/  # Frontend web interface
│   └── requirements.txt       # Python dependencies
├── .env                       # Environment configuration (not committed)
├── .env.example              # Environment template
└── README.md                 # This file
```

## Quick Start

### 1. Clone & Setup

```bash
git clone <repository-url>
cd Cleanify

# Copy and configure environment
cp .env.example .env
# Edit .env to customize settings

# Install dependencies
cd cleanify
pip install -r requirements.txt
```

### 2. Run Backend Server

```bash
cd cleanify/simulation-backend
python src/main.py
```

Server starts on `http://localhost:5001`

### 3. Open Frontend

Open `cleanify/simulation-playground/index.html` in your browser.

## Environment Configuration

### Distance Dispatch Parameters

Distance-only dispatch is tuned via the following environment variables:

```env
# Enable/disable the distance planner (leave enabled unless debugging)
USE_DISTANCE_DISPATCH=True

# Radius (meters) for tagging "nearby" bins during opportunistic pickups
DISPATCH_NEARBY_RADIUS_M=1500

# Minutes a bin stays protected after collection to avoid re-dispatch
DISPATCH_COOLDOWN_MIN=30

# Upper bound on bins per generated route
DISPATCH_MAX_ROUTE_BINS=10

# Percent of truck capacity kept in reserve (safety margin)
DISPATCH_CAPACITY_BUFFER_PERCENT=5

# Average driving speed (km/h) used for ETA estimates
DISPATCH_SPEED_KMH=28

# Optional urgency-score weights (higher = more influence)
URGENCY_WEIGHT_FILL=0.5
URGENCY_WEIGHT_RATE=0.3
URGENCY_WEIGHT_TIME=0.2
```

### Server & Services

```env
# Flask Server
HOST=0.0.0.0
PORT=5001
FLASK_ENV=development
FLASK_DEBUG=True

# External Routing Services
OSRM_URL=http://localhost:5000   # Route optimization
VROOM_URL=http://localhost:3000  # Vehicle routing

# Optimization
VROOM_TIMEOUT=10
VROOM_FALLBACK_ENABLED=True
```

### Tuning for Different Scenarios

| Scenario | Recommended Tweaks |
| --- | --- |
| **Urban core** | Lower `DISPATCH_NEARBY_RADIUS_M` (≤1000) to keep trips short. |
| **Suburban** | Default radius (1500) with standard urgency weights. |
| **Rural / spread out** | Increase `DISPATCH_NEARBY_RADIUS_M` (2000+) and bump `URGENCY_WEIGHT_TIME` to favor stale bins. |

Lower radii keep dispatches ultra-local, while higher radii encourage trucks to 
pick up additional bins during long return legs.

## Features

### Core Capabilities
- ✅ **Real-time Simulation**: Simulate waste collection operations
- ✅ **AI-Powered Routing**: Optimal truck dispatch and routing
- ✅ **Distance Dispatch Planner**: Prioritizes bins purely by urgency and distance
- ✅ **Dynamic Thresholds**: Bins trigger collection based on fill level
- ✅ **Traffic-Aware Dispatch**: Considers time-of-day traffic patterns
- ✅ **Proactive Collection**: Collects nearby bins to prevent duplicates

### Anti-Duplication System
- Tracks active dispatch recommendations and queue entries
- Notifies backend when bins are collected
- Prevents multiple trucks being sent to the same bin concurrently
- Clears queue entries when collection completes

### Optimization Features
- **VROOM Integration**: Vehicle routing optimization
- **OSRM Integration**: Real-world routing and distances
- **Capacity Management**: Prevents truck overload
- **Collection Queue**: Prioritizes bins by urgency
- **Route Extensions**: Collects nearby bins during return trips

## Architecture

### Backend (Flask)
- **Agent Service**: AI decision-making and coordination
- **Dispatch Planner Service**: Builds distance-only pickup plans and queues
- **Distance Cache Service**: Caches bin↔depot distances for quick scoring
- **Decision Service**: Routing optimization with VROOM or fallback heuristics
- **Simulation Service**: Time-based state updates

### Frontend (JavaScript)
- Interactive map visualization
- Real-time simulation control
- Bin and truck status monitoring
- Route visualization
- Collection queue display

### External Services
- **OSRM**: Open Source Routing Machine (optional)
- **VROOM**: Vehicle Routing Open-source Optimization Machine (optional)

## API Endpoints

### Simulation
- `POST /api/start_simulation` - Start simulation
- `POST /api/simulation_step` - Advance simulation time

### AI Decisions
- `POST /api/truck_routing` - Get routing decisions
- `POST /api/bin_reached_dt` - Handle bin reaching threshold
- `POST /api/bins_collected` - Notify bins collected
- `POST /api/update_truck_assignment` - Update truck status
- `GET /api/collection_queue` - Get current queue

### Data Management
- `POST /api/bin`, `PUT /api/bin`, `DELETE /api/bin` - Bin CRUD
- `POST /api/truck`, `PUT /api/truck`, `DELETE /api/truck` - Truck CRUD
- `POST /api/depot`, `PUT /api/depot`, `DELETE /api/depot` - Depot CRUD
- `POST /api/batch_sync` - Batch update all entities

### File Operations
- `GET /api/load_system/<filename>` - Load saved system
- `POST /api/save_system` - Save current system
- `GET /api/saved_files` - List saved systems

## Development

### Running Tests

```bash
cd cleanify/simulation-backend
pytest test/
```

### Debug Logging

Enable detailed logging in `src/main.py`:

```python
logging.basicConfig(level=logging.DEBUG)
```

### Adding New Features

1. **Backend**: Add to `src/services/` or `src/api/routes/`
2. **Frontend**: Update `simulation-playground/script.js`
3. **Configuration**: Add to `.env` and document in README

### Troubleshooting

### Agent keeps resetting / queue rebuilt too often
- Ensure only one `WasteCollectionAgent` instance exists (see `agent_manager.py`).
- Verify callers reuse the agent instead of instantiating per request.
- Queue rebuilds should align with routing cycles; frequent resets indicate duplicate agents.

### Duplicate truck dispatches
- Ensure `/bins_collected` endpoint is called after collection
- Check dispatch planner logs for `collection_queue` anomalies
- Verify trucks report status updates so the queue can release bins

### OSRM/VROOM unavailable
- Backend has fallback routing if services are down
- Set `VROOM_FALLBACK_ENABLED=True` in `.env`
- Check service URLs in configuration

## Contributing

1. Create feature branch: `git checkout -b feature-name`
2. Make changes and test thoroughly
3. Update documentation and environment examples
4. Submit pull request with description

## License

© 2025 Cleanify Team

---

**Need Help?** Check the logs for detailed debugging information. The backend logs dispatch recommendations, queue rebuilding, and route optimization steps.
