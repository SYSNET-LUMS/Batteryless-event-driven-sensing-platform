# Distance-Based Dispatch Playbook

## 1. Executive Summary

- **Single source of truth** – `DistanceCacheService` stores deterministic
  bin↔bin and bin↔depot distances for every downstream decision.
- **Capacity-aware triggers** – When a bin crosses its threshold, the planner
  looks outward using cached distances, filters for availability/capacity, and
  builds a plan that fits completely inside one truck.
- **Route-first execution** – Trucks leave the depot with a full
  `depot → bins → depot` itinerary (with ETA/load projections); no mid-route
  improvisation or clustering heuristics remain.

## 2. Goals & Constraints

| Goal | Description |
| --- | --- |
| Deterministic dispatch | Use only coordinates, fill data, and cached distances to make routing decisions. |
| Capacity awareness | Never overload trucks; calculate liters before committing to a route. |
| Opportunistic pickups | Pull in nearby bins when capacity allows to reduce redundant trips. |
| Full-route computation | Always output a round-trip route so the frontend and simulation stay in sync. |
| Extensibility | Keep the planner modular so additional heuristics or external services can be slotted in. |

## 3. Architecture Overview

```
┌──────────────────┐     ┌────────────────────┐
│ System Repository│◄────┤ Agent + REST Layer │
└────────┬─────────┘     └──────────┬─────────┘
         │ triggers                 │
         ▼                          ▼
   ┌─────────────┐        ┌────────────────────┐
   │DistanceCache│◄──────►│Dispatch Planner    │
   └──────┬──────┘        │(capacity + routing)│
          │               └─────┬──────────────┘
          │                     │
          ▼                     ▼
   ┌───────────────┐   ┌──────────────────────┐
   │OptimizationSvc│   │DecisionService (VROOM│
   └───────────────┘   │ + fallback routing)  │
                        └──────────────────────┘
```

## 4. Distance Intelligence Layer

1. **Warm-up** – `DistanceCacheService.warm_cache(bins, depots)` runs on system
   loads and bulk syncs.
2. **Incremental refresh** – Bin/depot mutations trigger targeted cache updates.
3. **API surface** – `get_bin_neighbors`, `get_distance_between_bins`, and
   `get_nearest_depot_for_bin` power the planner.

## 5. Dispatch Flow (per trigger)

1. **Trigger** – `/api/bin_reached_dt` or `/api/truck_routing` calls the planner.
2. **Validation** – Ensure bins/depots/trucks exist and at least one truck is idle
   with sufficient capacity.
3. **Candidate discovery** – Query neighbors within
   `DISPATCH_NEARBY_RADIUS_M`, filter by fill %, cooldown, and queue state.
4. **Capacity ordering** – Sort by urgency score
   (fill, fill rate, distance weight) and add until capacity buffer is reached.
5. **Route building** – Pass selected bins to `DecisionService`; VROOM is used
   when available; otherwise `_fallback_optimization()` emits a deterministic
   greedy route.
6. **Response** – Return a payload containing `status`, `truck_id`,
   `selected_bins`, `route`, `distance_km`, `eta_minutes`, and a `reason`.

## 6. Algorithms in Detail

### 6.1 Urgency Scoring
```python
def urgency_score(bin, distance_m, radius_m):
    fill = bin['fillLevel'] / 100.0
    fill_rate = min(bin.get('fillRate', 0) / 10.0, 1.0)
    distance_weight = max(0.0, 1.0 - distance_m / max(radius_m, 1.0))
    return (
        Config.URGENCY_WEIGHT_FILL * fill +
        Config.URGENCY_WEIGHT_RATE * fill_rate +
        Config.URGENCY_WEIGHT_TIME * distance_weight
    )
```

### 6.2 Capacity Guardrails
```python
available = truck_capacity - current_load
available -= truck_capacity * (Config.DISPATCH_CAPACITY_BUFFER_PERCENT / 100)
```
Always include the trigger bin, even if no other bins fit. If the trigger alone
exceeds capacity, return `status: "no_truck_available"`.

### 6.3 Routing
- **Primary** – `OptimizationService.optimize_truck_routes_with_vroom()`.
- **Fallback** – Greedy nearest-neighbor + 2-opt refinement with straight-line
  distance. Output always closes the loop back to the depot.

## 7. Service Interfaces

| Service | Responsibility |
| --- | --- |
| `DistanceCacheService` | Maintains canonical coordinate data and neighbor lookups. |
| `DispatchPlannerService` | Main entry point for bin triggers; enforces cooldown and capacity. |
| `OptimizationService` | Provides urgency scoring and orchestrates VROOM submissions. |
| `DecisionService` | Calls VROOM or fallback routing and annotates routes. |
| `AgentService` | Rebuilds queues, calls the planner, and syncs results with the frontend. |

## 8. Configuration Reference

```env
USE_DISTANCE_DISPATCH=true
DISPATCH_NEARBY_RADIUS_M=1500
DISPATCH_COOLDOWN_MIN=30
DISPATCH_MAX_ROUTE_BINS=10
DISPATCH_CAPACITY_BUFFER_PERCENT=5
DISPATCH_SPEED_KMH=28
VROOM_TIMEOUT=10
URGENCY_WEIGHT_FILL=0.5
URGENCY_WEIGHT_RATE=0.3
URGENCY_WEIGHT_TIME=0.2
```

## 9. Observability

- **Logs** – Planner logs `{trigger_bin, neighbors_considered, selected_bins,
  capacity_used, distance_km}`. Decision service logs VROOM requests/results.
- **Metrics** – Recommended Prometheus counters:
  - `distance_dispatch_selected_bins_count`
  - `distance_dispatch_route_distance_km`
  - `distance_dispatch_eta_minutes`
  - `distance_dispatch_failures_total{reason}`

## 10. Operational Checklist

1. Keep `USE_DISTANCE_DISPATCH=true` in all environments.
2. Monitor dispatch failure metrics for spikes >5% over 5 minutes.
3. After `/api/load_system`, verify `DistanceCacheService` warmed successfully.
4. Ensure `/api/bin_reached_dt`, `/api/truck_routing`, and `/api/collection_queue`
   all route through the planner, not legacy helpers.
5. Run pytest suites that cover planner success, capacity edge cases, cache
   warming, and fallback routing.

## 11. Future Enhancements

- Swap the greedy fallback with OR-Tools VRP for large fleets.
- Cache OSRM/VROOM travel times alongside geometric distances.
- Allow operators to pin bins into the queue manually for ad-hoc runs.
- Support multi-depot selection (choose the best depot per trigger).

With the distance-first pipeline, the dispatch engine is easier to reason about
and directly aligned with the physical constraints of bins, depots, and trucks.
