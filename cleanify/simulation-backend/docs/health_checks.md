# OSRM / VROOM / Cache Health Checks

This document explains how to run the automated checks that were promised for the Dec 14 milestone.
They provide reproducible evidence that external services are reachable and that the distance-cache pipeline
meets the expected build times.

## 1. API-level health

| Endpoint | Purpose | Notes |
| --- | --- | --- |
| `GET /api/health` | Lightweight liveness probe used by load balancers. | Returns `{status,message,version}` only. |
| `GET /api/health/full?iterations=3` | **New.** Runs the `ServiceHealthReporter` inside the Flask app and returns OSRM/VROOM availability, latency samples, and cache rebuild benchmarks. | `iterations` controls how many forced cache rebuilds are recorded. |
| `GET /api/distance_matrix/status` | Historical snapshot of the last build; handy for dashboards. | Does not trigger rebuilds—read only. |
| `GET /api/osrm_debug` | Raw counters from `OSRMService` (cache hits, total requests, etc.). | Pair with `/api/osrm_debug/reset` before targeted tests. |

## 2. CLI: `scripts/run_health_checks.py`

The CLI reproduces the same checks without hitting the HTTP API. It spins up the Flask app in-process,
executes the reporter, and prints JSON so you can store metrics in CI artifacts.

```bash
cd /home/khuzaima/Cleanify/Cleanify
python cleanify/simulation-backend/scripts/run_health_checks.py --iterations 3 --pretty
```

Example output snippet:
```jsonc
{
  "timestamp": 1734225600.12,
  "osrm": {
    "available": true,
    "latency_ms_avg": 18.4,
    "latency_ms_p95": 19.2,
    "probe_pairs": 2
  },
  "vroom": {
    "available": true,
    "latency_ms": 5.1,
    "url": "http://localhost:3000"
  },
  "distance_cache": {
    "performance": {
      "iterations": 3,
      "avg_build_seconds": 0.42
    }
  }
}
```

Add `--output reports/health.json` if you want the script to write the raw JSON to disk.

## 3. Using saved systems for load/perf trials

To benchmark cache rebuilds against a known workload, load one of the larger snapshots under
`saved_systems/` (e.g., `23_large_scale_50_bins.json`) and then rerun the CLI or hit `/api/health/full?iterations=5`.
The response will include `performance.runs[*].total_entries` so you can compare apples-to-apples across days.

## 4. Alerts & remediation

- **OSRM unavailable?** The report shows `available=false` and zero latency samples. Check Docker container or network route.
- **VROOM unavailable?** Dispatch falls back to the single-bin strategy; health output highlights that so you can react quickly.
- **Cache rebuild slow?** Use the per-run timings to see if the slowdown comes from OSRM latency (spikes in the OSRM section)
or from Python processing (high `build_seconds_measured` but normal OSRM latency).

These checks replace the ad-hoc manual curls we were performing earlier and give CI/CD a reliable hook
for validating infra dependencies before demo days.
