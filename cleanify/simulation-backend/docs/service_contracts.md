# Service Contracts – API + VROOM (Dec 2025)

This note captures the externally visible contracts that were finalized for the minimalist backend refactor.
It is intended to complement the inline code comments and provide a stable hand-off artifact for the product team.

## 1. REST API surface snapshot

| Area | Method | Endpoint | Notes |
| --- | --- | --- | --- |
| System | GET | `/api/health` | Liveness probe (returns version + status only). |
| System | GET | `/api/health/full` | New comprehensive report – exposes OSRM/VROOM/cache metrics and benchmark output. |
| System | POST | `/api/initialize` | Resets repository + schedules + distance cache (irreversible). |
| System | GET/POST | `/api/osrm_debug`, `/api/osrm_debug/reset` | Raw OSRM instrumentation counters + cache sizes, plus a reset hook. |
| System | GET | `/api/distance_matrix/status` | Last distance-matrix build summary + cache entry counts. |
| Config | GET | `/api/config` | Runtime knobs (thresholds, dispatch weights, capacity defaults). |
| Config | GET | `/api/config/simulation_start_hour` | Convenience helper for UI clocks. |
| Config | GET | `/api/config/traffic_info?simulation_time=` | Returns heavy/light traffic classification for the provided timestamp. |
| Items | POST/PUT/DELETE | `/api/bin\|truck\|depot` | CRUD with validation + automatic cache rebuild triggers. |
| Batch | POST | `/api/batch_sync` | Replace every bin/truck/depot atomically (used by importer and tests). |
| Files | POST | `/api/save_system` | Snapshot the repository into `saved_systems/`. |
| Files | GET | `/api/load_system/<filename>` | Reload a snapshot (also rebuilds caches). |
| Files | GET | `/api/saved_files` | List available snapshots. |
| Simulation | POST | `/api/start_simulation` | Guard: ensures repo has bins+depots (no long-running worker). |
| Simulation | POST | `/api/simulation_step` | Advance fill levels by each bin’s `fillRate`. |
| Simulation | POST | `/api/route` | OSRM geometry between two arbitrary points (for UI map). |
| Dispatch | POST | `/api/dispatch` | End-to-end dispatcher (traffic gate + urgency scoring + VROOM). |
| Dispatch | POST | `/api/bins_collected` | Mark bins empty + release truck capacity. |
| Dispatch | POST | `/api/update_truck_status` | Transition truck states (`idle`, `dispatching`, etc). |
| Schedules | GET/POST | `/api/schedules` | CRUD manual dispatch schedules. |
| Schedules | PUT/DELETE | `/api/schedules/<id>` | Update/remove schedule definitions. |
| Schedules | GET | `/api/schedules/active` | Filter schedules ready to run at `simulation_time`. |
| Schedules | POST | `/api/schedules/<id>/execute` | Force-run a schedule now. |

_All routes share the single `SystemRepository` instance attached to the Flask app, so changes are instantly visible everywhere._

## 2. VROOM I/O contract

### Payload we send
- **Jobs**: One per undispatched bin.
  - `delivery`: Real liters (`capacity * fillLevel%`).
  - `service`: Fixed **300 seconds** (5 min) dwell time to keep payload deterministic.
  - `priority`: `urgency_score` (0‑100). Falls back to fill level when the score is absent.
  - `time_window`: **Only for critical bins** (≥90% full _or_ <1 hour to overflow). The window spans the next 60 minutes of the simulation clock.
- **Vehicles**: One per idle truck.
  - `start`/`end`: Depot coordinates (always round trips for now).
  - `capacity`: Truck capacity liters so VROOM respects actual load limits.
  - `profile`: `car` (OSRM driving profile).

### Response we read
- Map numeric vehicle IDs back to `TRUCK_*` via the `vehicle_map` generated during payload construction.
- Map numeric job IDs back to `BIN_*` via the `job_map`.
- Emit `{truck_id, bin_ids, distance, duration}` for each successful route, then flip those trucks/bins into the `dispatching` state to block duplicate dispatches.
- If VROOM fails, `_simple_fallback` sends each truck to at most one bin so the UI still shows progress and bins leave the "urgent" list.

### Why these choices?
1. **Urgency-based priority** keeps fast-fill, medium-volume bins from starving behind giant but slow bins.
2. **Liter-based deliveries** force multi-truck routing when a single route cannot physically hold the waste.
3. **Critical-only time windows** spotlight emergencies without over-constraining the solver during normal hours.
4. **Fixed service time** simplifies solver payloads until we gather real pickup-duration telemetry.

## 3. Decision log (Dec 11–14)
- **Dec 11** – API inventory captured (table above) and the VROOM contract formalized.
- **Dec 12** – Broken legacy pytest suites were removed; only `test/test_vroom_service.py` remains as regression coverage for liter-based deliveries.
- **Dec 13** – Time-window policy locked to "critical bins only"; service time fixed at 300 s.
- **Dec 14** – Priority formula anchored to `urgency_score`; OSRM/VROOM/cache health checks mandated (see `docs/health_checks.md`).

Keeping this document in the repo removes ambiguity when onboarding new engineers or syncing with the product spec.
