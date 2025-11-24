# Truck Dispatching Logic

The dispatch system now runs entirely on **distance and urgency data**. Each
recommendation is derived from telemetry → cache → planner → VROOM without any
clustering, centroid math, or geo-zones. This document explains how the pipeline
decides when to dispatch, which bins to collect, and how routes are produced.

---

## Architecture Layers

| Layer | Responsibility |
| --- | --- |
| **Simulation / Telemetry** | Emits bin fill levels, timestamps, and truck status updates. |
| **WasteCollectionAgent** | Normalizes events, applies dynamic thresholds, and publishes dispatch intents. |
| **DistanceCacheService** | Maintains rolling matrices for bin↔truck and bin↔depot distances using OSRM snapshots. |
| **DispatchPlannerService** | Scores bin candidates, enforces cooldowns/capacity, and chooses the truck/bundle to attempt. |
| **OptimizationService (VROOM wrapper)** | Converts the chosen bundle into a route; rejects if infeasible. |
| **DecisionService & API** | Surfaces the recommendation, logs context, and feeds the simulator/UI. |

Each call moves forward through these services—there are no branching code paths
for clusters or legacy heuristics anymore.

---

## Dispatch Flow

1. **Bin telemetry arrives** with current fill %, fill rate, and projected hours
     to overflow. The WasteCollectionAgent compares it against the bin’s dynamic
     threshold and global overrides.
2. **Pre-filtering** drops bins currently cooling down or already assigned to an
     active truck. Remaining bins become candidates.
3. **Distance enrichment** asks `DistanceCacheService` for:
     - nearest trucks that can physically reach the bin,
     - nearby bins (within `DISPATCH_NEARBY_RADIUS_M`) that could be bundled,
     - shortest path back to the depot for payload validation.
4. **Scoring** inside `DispatchPlannerService` computes a weighted urgency score
     per bin:
     - 50% → current fill percentage vs. threshold,
     - 30% → hours to overflow (based on fill rate),
     - 20% → distance from the candidate truck.
     Flags allow the planner to bump urgency if a bin is marked critical or if the
     site is under service-level agreements.
5. **Truck selection** sorts available trucks by proximity, cooldown, and free
     capacity. The first viable truck becomes the anchor for bundling.
6. **Bundle assembly** greedily adds nearby bins while:
     - keeping total liters ≤ truck capacity × `DISPATCH_CAPACITY_BUFFER_PERCENT`,
     - respecting `MAX_BINS_PER_RUN`,
     - ensuring each bin still meets `MIN_BIN_SCORE` after bundling.
7. **OptimizationService** sends the truck, starting depot, and ordered bins to
     VROOM. If VROOM returns a valid route, the decision becomes “dispatch now.” If
     optimization fails, the planner tries the next truck (if any) or returns a
     defer decision with context.
8. **DecisionService** stores the payload (truck id, route geometry, reason
     codes) so the simulator/frontend/tracking dashboard can consume it.

---

## Candidate Scoring Details

| Component | Formula | Notes |
| --- | --- | --- |
| Fill % | `fill_level / dynamic_threshold` | Capped at 1.2 to limit runaway scores. |
| Fill rate | `hours_to_overflow = (max_capacity - current_fill) / fill_rate` | Inverse is normalized to [0, 1]. |
| Proximity | `distance_to_truck / DISPATCH_NEARBY_RADIUS_M` | Lower distance = higher score contribution. |

- Scores below `MIN_BIN_SCORE` (default 0.55) are ignored.
- Any bin predicted to overflow within `EMERGENCY_OVERFLOW_HOURS` bypasses the
    cooldown and forces dispatch regardless of traffic settings.
- Planner records the full breakdown for debugging via structured logs.

---

## Routing Outcomes

The OptimizationService normalizes the request into VROOM’s single-vehicle TSP:

```json
{
    "vehicles": [{
        "id": 7,
        "start": [depot_lon, depot_lat],
        "capacity": [truck_capacity_liters]
    }],
    "jobs": [
        {"id": 201, "service": 180, "location": [bin_lon, bin_lat], "delivery": [bin_volume]},
        ...
    ]
}
```

- If VROOM succeeds, we persist:
    - ordered bin list,
    - polyline geometry for the UI,
    - ETA per stop (used by the simulator for timing adjustments).
- When VROOM rejects (rare, usually due to stale coordinates), the planner marks
    the decision as `wait_distance_error` so observability tools can highlight the
    mismatch.

The simulator consumes the ordered bins verbatim; there is no additional
cluster- or centroid-based reshuffling anywhere.

---

## Edge Cases & Safeguards

| Scenario | Behavior |
| --- | --- |
| **No trucks free** | Planner returns `wait_no_trucks` with next eligible time. |
| **Distance cache miss** | Falls back to live OSRM query and memoizes the result. |
| **Traffic throttling** | If `traffic_density > TRAFFIC_HEAVY_THRESHOLD` and no bin is in emergency, planner delays dispatch up to `TRAFFIC_MAX_DELAY_MIN`. |
| **Cooldown violation** | Bins recently serviced are skipped until `DISPATCH_COOLDOWN_MIN` expires. |
| **Capacity overflow** | Greedy bundling simply stops before exceeding allowed liters, prioritizing highest-score bins first. |

---

## Configuration Surface

| Variable | Default | Description |
| --- | --- | --- |
| `USE_DISTANCE_DISPATCH` | `true` | Master toggle; nothing else runs if disabled. |
| `DISPATCH_NEARBY_RADIUS_M` | `1500` | Search radius for bundling bins. |
| `DISPATCH_COOLDOWN_MIN` | `45` | Minimum minutes between visits per bin. |
| `DISPATCH_CAPACITY_BUFFER_PERCENT` | `0.85` | Keeps some headroom so trucks do not exceed physical limits. |
| `EMERGENCY_OVERFLOW_HOURS` | `2` | Force-dispatch threshold regardless of traffic. |
| `TRAFFIC_HEAVY_THRESHOLD` | `5.0` | Density above which planner may defer if safe. |
| `MAX_BINS_PER_RUN` | `6` | Upper bound to keep VROOM problem size tiny. |

Tune these via environment variables or `.env` when running locally. The README
lists the same values so operators have a single source of truth.

---

## Observability Hooks

- **Structured logs** (`dispatch_planner.log`) include bin ids, truck ids, score
    breakdown, and reason codes.
- **Saved systems** (`simulation-backend/saved_systems/*.json`) capture the exact
    state before/after a decision for replaying scenarios.
- **Debug toggles** allow forcing traffic loads or disabling the optimization
    step to isolate planner behavior during tests.

---

## Migration Notes

- Delete any modules importing `ClusteringService`, centroid math, or
    zone-based dispatch—they are unused and should not be referenced.
- Rewrite tests that depended on cluster fixtures. Replace them with
    telemetry-driven cases that assert urgency scoring and routing bundles.
- Old endpoints such as `/api/update_truck_assignment` are thin shims now; they
    simply acknowledge planner results to avoid breaking older clients.
- Documentation (README, Distance_Based_Dispatch, this file) must only describe
    distance-first behavior. If you see words like “cluster,” “zone,” or
    “proactive grouping,” assume the content is stale and remove it.

With these notes applied, the truck dispatch pipeline remains deterministic,
auditable, and free of any legacy clustering assumptions.
