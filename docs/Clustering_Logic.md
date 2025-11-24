# Geo-Zone Clustering Logic

## Overview

The clustering system now groups bins using a **geo-zone** technique instead of
the previous depot-based radius approach. Every bin is projected into metric
space, snapped to a square grid, and then merged/split to produce compact,
balanced workloads that do not depend on depot placement.

- **File**: `cleanify/simulation-backend/src/services/clustering_service.py`
- **Class**: `ClusteringService`
- **Main method**: `create_simple_dynamic_clusters()`

---

## Algorithm Steps

### 1. Normalize & Project

```python
lat_rad = math.radians(bin['lat'])
lng_rad = math.radians(bin['lng'])
x = EARTH_RADIUS_M * lng_rad
y = EARTH_RADIUS_M * math.log(math.tan(math.pi / 4 + lat_rad / 2))
```

Each bin dictionary receives `lat`, `lng`, `id`, and `_xy` fields so down-stream
layers (agent, proactive dispatch, analytics) always see a consistent shape.

### 2. Zone Bucketing

```python
zone_x = int(x // CLUSTER_ZONE_SIZE_M)
zone_y = int(y // CLUSTER_ZONE_SIZE_M)
zone_map[(zone_x, zone_y)].append(bin)
```

All bins in the same zone form a **base cluster**. The zone size defaults to
`600 m` and can be tuned via `CLUSTER_ZONE_SIZE_M`.

### 3. Split Oversized Zones

If a zone holds more than `CLUSTER_MAX_BIN_COUNT` bins (default `12`), it is
sorted by `fillLevel` and split into evenly sized chunks. This guarantees that a
single truck is never assigned an impossible stop list.

### 4. Merge Sparse Zones

Clusters with fewer than `CLUSTER_MIN_BIN_COUNT` bins *or* combined fill below
`CLUSTER_MIN_FILL_PERCENT` are considered sparse. Each sparse cluster looks for
the nearest dense cluster. If the centroid-to-centroid distance is below
`CLUSTER_ZONE_SIZE_M × CLUSTER_MERGE_DISTANCE_MULTIPLIER`, the clusters are
merged; otherwise the sparse cluster remains independent (useful for isolated
rural bins).

### 5. Emit Quality Metrics

`get_cluster_info()` produces:

- `center` (average lat/lng)
- `radius_m` (max distance to center)
- `quality_metrics`
  - `compactness_score`
  - `load_balance_score`
  - `coverage_score`
  - `collection_efficiency`
  - `quality_rating` (`excellent`/`good`/`fair`/`sparse`)

These metrics feed the dashboards, logs, and regression tests.

---

## Configuration Reference

| Variable | Default | Effect |
| --- | --- | --- |
| `CLUSTER_ZONE_SIZE_M` | `600` | Size of each geo zone in meters |
| `CLUSTER_MAX_BIN_COUNT` | `12` | Split clusters once they exceed this many bins |
| `CLUSTER_MIN_BIN_COUNT` | `2` | Merge clusters that fall below this bin count |
| `CLUSTER_MIN_FILL_PERCENT` | `20` | Merge clusters whose combined fill is below this % |
| `CLUSTER_MERGE_DISTANCE_MULTIPLIER` | `1.5` | Maximum centroid distance (in zone widths) for merging |

The previous `DEPOT_DISTANCE_PERCENTAGE` / `MAX_BIN_RADIUS_M` variables are no
longer used; compatibility stubs remain so existing dashboards keep working.

---

## Example

Given 9 bins across ~2 km with `CLUSTER_ZONE_SIZE_M=600`:

1. Bins 1–3 fall into zone `(12540, 18420)` → Cluster A.
2. Bins 4–6 sit inside two adjacent zones; because each zone is under the fill
   minimum, they merge into Cluster B.
3. Bins 7–9 are >1.2 km away; they get their own cluster.

Resulting summary (`get_cluster_info`):

| Cluster | Size | Radius (m) | Quality |
| --- | --- | --- | --- |
| 0 | 3 | 190 | excellent |
| 1 | 4 | 420 | good |
| 2 | 2 | 160 | fair |

---

## Edge Cases

| Scenario | Handling |
| --- | --- |
| **No depots provided** | No longer required; clustering ignores depots |
| **Single bin** | Immediately returned as `{0: [bin]}` |
| **Isolated bin** | Remains its own cluster if no dense neighbor exists |
| **Large deployments** | Automatic splitting ensures truck manifests stay within `CLUSTER_MAX_BIN_COUNT` |
| **Missing lat/lng** | Bin is skipped, and the service logs the issue when `debug_enabled` is `True` |

---

## Complexity & Performance

- **Projection & bucketing**: `O(n)`
- **Splitting**: `O(n log n)` for the per-zone sort (worst-case when a single
  zone has many bins)
- **Merging**: `O(n)` because each sparse cluster scans the dense cluster list
  once

Total runtime remains well within a few milliseconds for the 100–500 bin systems
used in the simulator.

---

## Testing

Dedicated pytest coverage now lives in `test/test_zone_clustering.py`:

```bash
pytest test/test_zone_clustering.py
```

The suite verifies:

1. Deterministic zone bucketing
2. Splitting of large clusters
3. Automatic merging of sparse clusters
4. Quality metric payloads

Run `pytest test/` to execute the entire backend test suite when validating a
release.
