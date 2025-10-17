# Cleanify - Smart Waste Collection System

AI-powered waste collection system with intelligent routing, clustering optimization, and real-time simulation.

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

### Clustering Parameters

Control how bins are grouped for efficient collection:

```env
# Percentage of depot distance for bin service radius (0.0-1.0)
DEPOT_DISTANCE_PERCENTAGE=0.35

# Maximum bin service radius in meters
MAX_BIN_RADIUS_M=2000

# Default radius when no depot available
DEFAULT_BIN_RADIUS_M=1400
```

**How it works:**
- Each bin gets a service radius based on distance to nearest depot
- Bins within each other's radius form a cluster
- Trucks collect entire clusters efficiently

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

**Urban Dense Areas** (many bins close together):
```env
DEPOT_DISTANCE_PERCENTAGE=0.30
MAX_BIN_RADIUS_M=1500
DEFAULT_BIN_RADIUS_M=1200
```

**Suburban Areas** (balanced):
```env
DEPOT_DISTANCE_PERCENTAGE=0.35
MAX_BIN_RADIUS_M=2000
DEFAULT_BIN_RADIUS_M=1400
```

**Rural Areas** (bins spread out):
```env
DEPOT_DISTANCE_PERCENTAGE=0.45
MAX_BIN_RADIUS_M=3000
DEFAULT_BIN_RADIUS_M=2000
```

## Features

### Core Capabilities
- ✅ **Real-time Simulation**: Simulate waste collection operations
- ✅ **AI-Powered Routing**: Optimal truck dispatch and routing
- ✅ **Smart Clustering**: Geographic bin grouping for efficiency
- ✅ **Dynamic Thresholds**: Bins trigger collection based on fill level
- ✅ **Traffic-Aware Dispatch**: Considers time-of-day traffic patterns
- ✅ **Proactive Collection**: Collects nearby bins to prevent duplicates

### Anti-Duplication System
- Tracks active cluster assignments
- Notifies backend when bins are collected
- Prevents multiple trucks dispatching to same cluster
- Clears assignments when collection completes

### Optimization Features
- **VROOM Integration**: Vehicle routing optimization
- **OSRM Integration**: Real-world routing and distances
- **Capacity Management**: Prevents truck overload
- **Collection Queue**: Prioritizes bins by urgency
- **Route Extensions**: Collects nearby bins during return trips

## Architecture

### Backend (Flask)
- **Agent Service**: AI decision-making and coordination
- **Clustering Service**: Proximity-based bin grouping
- **Proactive Dispatch**: Prevents duplicate dispatches
- **Decision Service**: Routing optimization with VROOM
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

## Troubleshooting

### Agent keeps resetting / Clusters recalculating
- Check for unwanted `invalidate_cluster_cache()` calls
- Verify agent singleton is working (`agent_manager.py`)
- Clusters should only calculate once at simulation start

### Duplicate truck dispatches
- Ensure `/bins_collected` endpoint is called after collection
- Check proactive dispatch tracking in backend logs
- Verify cluster assignments are cleared properly

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

**Need Help?** Check the logs for detailed debugging information. The backend logs clustering decisions, dispatch logic, and route optimization steps.
