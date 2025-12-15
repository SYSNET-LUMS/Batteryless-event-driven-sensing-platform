# Cleanify Backend v2.0 – Dispatch + VROOM Contract

## 🚦 What this service does
- Stores the whole simulation state (bins, trucks, depots, schedules) inside a shared `SystemRepository`.
- Pre-computes depot↔bin↔bin road distances through `DistanceMatrixService` so downstream services never block on OSRM during dispatch.
- Scores every undispatched bin for urgency, classifies them, and decides if batching should wait or go now.
- Builds a global VROOM payload (all bins, all idle trucks) with deterministic constraints and posts it to the solver.
- Immediately updates trucks/bins to `dispatching` so duplicate routes cannot be queued.

That pipeline is intentionally linear—no agents, cron jobs, or background threads.

```
Client → /api/dispatch → distance matrix check → urgency scoring → VROOM →
routes returned + repository updated
```

---

## 🧱 Core services (src/services)
| Service | Responsibility |
| --- | --- |
| `traffic_service.py` | Computes heavy/light hours so dispatching can wait when overflow risk is low. |
| `distance_matrix_service.py` | Builds depot→bin, bin→depot, and bin↔bin caches via OSRM with haversine fallback. |
| `external/osrm_service.py` | Thin HTTP client for the OSRM `/route` API, plus instrumentation + caching. |
| `external/vroom_service.py` | Builds job/vehicle payloads, applies priority/time-window logic, parses VROOM responses. |
| `simulation/simulation_service.py` | Evolves bin fill levels & thresholds using cached distances + traffic rules. |
| `routing_service.py` | Returns OSRM geometry between two coordinates for the frontend map. |
| `file_service.py` | Saves/loads complete system snapshots under `saved_systems/`. |
| `schedule_service.py` | Stores pending/recurring manual schedules alongside real-time dispatching. |

---

## 🌐 API surface (src/api/routes)
| Area | Method | Endpoint | Purpose |
| --- | --- | --- | --- |
| System | GET | `/api/health` | Basic heartbeat. |
| System | POST | `/api/initialize` | Wipe repository + schedules and clear distance caches. |
| System | GET/POST | `/api/osrm_debug`, `/api/osrm_debug/reset` | Inspect/reset OSRM stats and cache sizes. |
| System | GET | `/api/distance_matrix/status` | View last build summary + cache entry counts. |
| Config | GET | `/api/config` | Share runtime defaults (capacities, dispatch knobs) with the UI. |
| Config | GET | `/api/config/simulation_start_hour` | Lightweight sync helper for the clock. |
| Config | GET | `/api/config/traffic_info?simulation_time=` | Returns density + hour snapshot based on BIN_1’s profile. |
| Items | POST/PUT/DELETE | `/api/bin\|truck\|depot` | CRUD entities with validation and auto cache rebuilds. |
| Batch | POST | `/api/batch_sync` | Replace all bins/trucks/depots in a single call, then rebuild caches. |
| Files | POST | `/api/save_system` | Persist the current state as a timestamped JSON. |
| Files | GET | `/api/load_system/<filename>` | Load a snapshot into the repository and rebuild caches. |
| Files | GET | `/api/saved_files` | List available saves. |
| Simulation | POST | `/api/start_simulation` | Guard to ensure bins + depots exist before simulating. |
| Simulation | POST | `/api/simulation_step` | Increment bin fill levels using each `fillRate`. |
| Simulation | POST | `/api/route` | Fetch OSRM geometry between two lat/lng pairs. |
| Dispatch | POST | `/api/dispatch` | Unified dispatcher (urgency scoring + VROOM + state updates). |
| Dispatch | POST | `/api/bins_collected` | Mark bins as emptied + free truck capacity. |
| Dispatch | POST | `/api/update_truck_status` | Flip truck state and release any unvisited bins. |
| Schedules | GET/POST | `/api/schedules` | List or create manual dispatch schedules. |
| Schedules | PUT/DELETE | `/api/schedules/<schedule_id>` | Update or remove a schedule. |
| Schedules | GET | `/api/schedules/active` | Return schedules ready to run at `simulation_time`. |
| Schedules | POST | `/api/schedules/<id>/execute` | Manually trigger a schedule run. |

These routes (registered in `src/api/app.py`) all share the same `system_repository`, so state changes are visible immediately across endpoints.

---

## 🚚 Dispatch + VROOM contract (Dec 11 deliverable)
### Input payload we send
```jsonc
{
  "jobs": [
    {
      "id": 1,
      "location": [lng, lat],
      "service": 300,
      "delivery": [liters_of_waste],
      "priority": 0-100,
      "time_window": [start_min, end_min]  // only for critical bins
    }
  ],
  "vehicles": [
    {
      "id": 1,
      "start": [depot_lng, depot_lat],
      "end": [depot_lng, depot_lat],
      "capacity": [truck_capacity_liters],
      "profile": "car"
    }
  ]
}
```
Key decisions:
1. **Priority formula** → `urgency_score` (0‑100) blending fill level, fill rate, and projected overflow time. If a bin lacks the score we fall back to `fillLevel`. This keeps fast-fill bins from starving even if they are not the fullest.
2. **Delivery units** → Actual liters (`capacity * fill%`). This forces VROOM to respect real truck capacity and engage additional trucks when one route would overflow.
3. **Service time** → Fixed **300 seconds (5 minutes)** per bin. Deterministic, small payload, easy to reason about.
4. **Time windows** → **Critical bins only** (≥90 % fill or <1 hr to overflow). Each gets a 60‑minute window starting at the current simulation clock. Everything else stays unconstrained for flexible batching.

### What we parse from VROOM
1. Map VROOM vehicle IDs back to `TRUCK_X` using the `vehicle_map`.
2. Collect job IDs from each route step and map them to `BIN_X` via `job_map`.
3. Return `{truck_id, bin_ids, distance, duration}` per route and mark trucks/bins as dispatching to prevent duplicates.
4. If VROOM errors, fall back to `_simple_fallback` (one bin per truck) so the UI still shows progress.

### Why this combination?
- **Urgency-based priority** favors bins that are both full and fast-filling.
- **Critical-only windows** highlight emergencies without over-constraining the solver.
- **Fixed service time** keeps payloads tiny until we need capacity-based dwell times.
- **Liter-based delivery** finally forces multi-truck dispatching in scenarios where a single truck cannot carry the load.

---

## 🧪 Tests (Dec 12 deliverable – broken suites removed)
All legacy tests referencing deleted services have been removed. The current regression coverage focuses on the VROOM payload builder so CI fails if we ever regress the liter-based deliveries.

```bash
cd /home/khuzaima/Cleanify/Cleanify
./venv/bin/python -m pytest test/test_vroom_service.py
```

Add more tests under `Cleanify/test/` following standard `pytest` discovery (`test_*.py`).

---

## ✅ Health checks & performance probes (Dec 14 deliverable)
- `GET /api/health/full?iterations=3` now publishes OSRM availability, VROOM health, and distance-cache rebuild timings in one response.
- `cleanify/simulation-backend/scripts/run_health_checks.py` runs the same reporter offline so CI can store JSON artifacts.
- See `docs/health_checks.md` for flow details and a sample output payload.

---

## ⚙️ Setup & runtime
```bash
# Install Python deps
pip install -r cleanify/requirements.txt

# Start OSRM
docker run -it -p 5000:5000 osrm/osrm-backend \
  osrm-routed --algorithm mld /data/pakistan-latest.osrm

# Start VROOM
docker run -it -p 3000:3000 vroomvrp/vroom
```

`.env` overrides (place inside `cleanify/simulation-backend/`):
```env
HOST=0.0.0.0
PORT=5001
OSRM_URL=http://localhost:5000
VROOM_URL=http://localhost:3000
TRAFFIC_HEAVY_HOURS=8,9,17,18
TRAFFIC_MULTIPLIER=1.5
TRAFFIC_BUFFER_HOURS=1.0
SIMULATION_START_HOUR=7
```

Run the backend:
```bash
cd cleanify/simulation-backend
python src/main.py
```

Frontend playground:
```bash
cd cleanify/simulation-playground
# open index.html (or use Live Server)
```

---

## 🐛 Troubleshooting quick hits
| Issue | Check |
| --- | --- |
| No routes generated | Ensure bins are undispatched + above threshold, trucks are `idle`, and a depot exists. |
| VROOM unavailable | `curl http://localhost:3000/health` – backend will print when the fallback is used. |
| OSRM unavailable | `curl http://localhost:5000/health`; start the Docker container if down. |
| Distance cache stale | Call `/api/distance_matrix/status` or rerun `/api/batch_sync`/`/api/load_system`. |

---

## 📌 Decision changelog (so everyone knows Taimour’s tasks were handled)
- **Dec 11:** API inventory completed; VROOM contract documented; urgency-based priority affirmed.
- **Dec 12‑14:** Legacy broken tests removed; liter-based delivery tests added; time-window (critical-only) and service-time (fixed 300 s) decisions locked.

See `docs/service_contracts.md` for the full API + VROOM contract snapshot beyond this README.

These notes replace the spreadsheet action items, so future work can build directly on the documented choices.
