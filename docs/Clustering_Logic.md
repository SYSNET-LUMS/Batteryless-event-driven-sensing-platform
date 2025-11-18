# Bin Clustering Formation Logic

## Overview
The clustering system groups nearby bins into geographic clusters to enable efficient multi-bin collection trips. Clusters are formed using proximity-based graph algorithms with adaptive radii based on depot distance.

## Location
**File**: `cleanify/simulation-backend/src/services/clustering_service.py`  
**Class**: `ClusteringService`  
**Main Method**: `cluster_bins_by_proximity()`

---

## Algorithm Type

**Graph-Based Connected Components**
- Each bin is a node
- Edges connect bins within proximity threshold
- Clusters are connected components in the graph

---

## Step-by-Step Process

### Phase 1: Compute Per-Bin Radii

#### Method: `_compute_per_bin_radii()`

**Purpose**: Calculate individual proximity radius for each bin based on distance to nearest depot.

```python
def _compute_per_bin_radii(bins, depots):
    per_bin_radii = {}
    
    for bin in bins:
        # 1. Find nearest depot
        min_depot_dist = min(
            calculate_distance_km(bin, depot) * 1000  # Convert to meters
            for depot in depots
        )
        
        # 2. Calculate radius as percentage of depot distance
        radius = min_depot_dist * DEPOT_DISTANCE_PERCENTAGE
        
        # 3. Apply upper bound cap
        radius = min(radius, MAX_BIN_RADIUS_M)
        
        # 4. Store result
        per_bin_radii[bin['id']] = radius
    
    return per_bin_radii
```

**Formula**:
```
radius_i = min(nearest_depot_distance × 0.35, 2000m)
```

#### Configuration Parameters

| Parameter | Default | Source | Description |
|-----------|---------|--------|-------------|
| `DEPOT_DISTANCE_PERCENTAGE` | 0.35 (35%) | `.env` | Radius as fraction of depot distance |
| `MAX_BIN_RADIUS_M` | 2000.0 m | `.env` | Maximum clustering radius |
| `DEFAULT_BIN_RADIUS_M` | 1400.0 m | `.env` | Fallback radius if calculation fails |

#### Example Radius Calculation

**Scenario**: Bin is 5000m from nearest depot
```
radius = 5000 × 0.35 = 1750m
capped_radius = min(1750, 2000) = 1750m
```

**Scenario**: Bin is 10000m from nearest depot
```
radius = 10000 × 0.35 = 3500m
capped_radius = min(3500, 2000) = 2000m  # Capped at maximum
```

---

### Phase 2: Build Proximity Graph

#### Method: `_cluster_by_proximity_per_bin()`

**Purpose**: Create adjacency graph where bins are connected if within proximity threshold.

```python
def _cluster_by_proximity_per_bin(bins, per_bin_radii):
    # 1. Initialize graph structure
    adjacency = {bin['id']: [] for bin in bins}
    bin_dict = {bin['id']: bin for bin in bins}
    
    # 2. Build edges (pairwise distance checks)
    for i, bin_i in enumerate(bins):
        for bin_j in bins[i+1:]:
            # Calculate distance between bins
            dist_m = calculate_distance_km(bin_i, bin_j) * 1000
            
            # Get radii for both bins
            radius_i = per_bin_radii[bin_i['id']]
            radius_j = per_bin_radii[bin_j['id']]
            
            # Connect if within either bin's radius
            if dist_m <= max(radius_i, radius_j):
                adjacency[bin_i['id']].append(bin_j['id'])
                adjacency[bin_j['id']].append(bin_i['id'])
    
    # 3. Find connected components (clusters)
    return _extract_connected_components(adjacency, bin_dict)
```

**Edge Condition**:
```
distance(bin_i, bin_j) ≤ max(radius_i, radius_j)
```

**Rationale**: Use the larger radius to handle asymmetric proximity (bin near depot vs bin far from depot).

---

### Phase 3: Extract Connected Components

#### Method: `_extract_connected_components()`

**Purpose**: Group bins into clusters using depth-first search (DFS) on the adjacency graph.

```python
def _extract_connected_components(adjacency, bin_dict):
    visited = set()
    clusters = []
    
    for bin_id in adjacency:
        if bin_id not in visited:
            # Start new cluster with DFS
            cluster = []
            stack = [bin_id]
            
            while stack:
                current = stack.pop()
                if current not in visited:
                    visited.add(current)
                    cluster.append(bin_dict[current])
                    
                    # Add neighbors to stack
                    stack.extend(adjacency[current])
            
            clusters.append(cluster)
    
    return clusters
```

**Algorithm**: Depth-First Search (DFS)
- **Time Complexity**: O(n + e) where n = bins, e = edges
- **Space Complexity**: O(n)

---

## Complete Example Walkthrough

### Input Data
```json
{
  "bins": [
    {"id": "BIN_1", "lat": 33.6092, "lng": 73.0825, "capacity": 500},
    {"id": "BIN_2", "lat": 33.6100, "lng": 73.0830, "capacity": 500},
    {"id": "BIN_3", "lat": 33.6095, "lng": 73.0827, "capacity": 500},
    {"id": "BIN_4", "lat": 33.6200, "lng": 73.0900, "capacity": 500}
  ],
  "depots": [
    {"id": "DEPOT_1", "lat": 33.6000, "lng": 73.0800}
  ]
}
```

### Step 1: Calculate Radii
```
BIN_1 to DEPOT_1: 1032m → radius = 1032 × 0.35 = 361m
BIN_2 to DEPOT_1: 1142m → radius = 1142 × 0.35 = 400m
BIN_3 to DEPOT_1: 1087m → radius = 1087 × 0.35 = 380m
BIN_4 to DEPOT_1: 2500m → radius = 2500 × 0.35 = 875m
```

### Step 2: Build Adjacency
```
Distances:
  BIN_1 ↔ BIN_2: 95m  ≤ max(361, 400) = 400m ✓ CONNECTED
  BIN_1 ↔ BIN_3: 45m  ≤ max(361, 380) = 380m ✓ CONNECTED
  BIN_1 ↔ BIN_4: 1950m ≤ max(361, 875) = 875m ✗ NOT CONNECTED
  BIN_2 ↔ BIN_3: 60m  ≤ max(400, 380) = 400m ✓ CONNECTED
  BIN_2 ↔ BIN_4: 1900m ≤ max(400, 875) = 875m ✗ NOT CONNECTED
  BIN_3 ↔ BIN_4: 1925m ≤ max(380, 875) = 875m ✗ NOT CONNECTED

Adjacency Graph:
  BIN_1: [BIN_2, BIN_3]
  BIN_2: [BIN_1, BIN_3]
  BIN_3: [BIN_1, BIN_2]
  BIN_4: []
```

### Step 3: Extract Clusters
```
DFS from BIN_1:
  Visit BIN_1 → neighbors: [BIN_2, BIN_3]
  Visit BIN_2 → neighbors: [BIN_1 (visited), BIN_3]
  Visit BIN_3 → neighbors: [BIN_1 (visited), BIN_2 (visited)]
  → Cluster 1: [BIN_1, BIN_2, BIN_3]

DFS from BIN_4:
  Visit BIN_4 → neighbors: []
  → Cluster 2: [BIN_4]
```

### Final Result
```python
[
    {
        "cluster_id": 0,
        "bins": [
            {"id": "BIN_1", "lat": 33.6092, "lng": 73.0825},
            {"id": "BIN_2", "lat": 33.6100, "lng": 73.0830},
            {"id": "BIN_3", "lat": 33.6095, "lng": 73.0827}
        ],
        "bin_count": 3,
        "total_capacity": 1500
    },
    {
        "cluster_id": 1,
        "bins": [
            {"id": "BIN_4", "lat": 33.6200, "lng": 73.0900}
        ],
        "bin_count": 1,
        "total_capacity": 500
    }
]
```

---

## Real System Example (Test Results)

From `cleanify_system_20251007_130200.json`:

### Cluster 0 (4 bins)
```
Bins: ['BIN_1', 'BIN_4', 'BIN_3', 'BIN_2']
Internal distances:
  BIN_1 ↔ BIN_4: 874.4m
  BIN_1 ↔ BIN_3: 1158.9m
  BIN_1 ↔ BIN_2: 932.8m
  BIN_4 ↔ BIN_3: 1145.1m
  BIN_4 ↔ BIN_2: 1746.8m
  BIN_3 ↔ BIN_2: 1401.8m
Max internal distance: 1746.8m
```

### Cluster 1 (3 bins)
```
Bins: ['BIN_5', 'BIN_6', 'BIN_7']
Internal distances:
  BIN_5 ↔ BIN_6: 842.3m
  BIN_5 ↔ BIN_7: 1489.4m
  BIN_6 ↔ BIN_7: 1299.1m
Max internal distance: 1489.4m
```

### Cluster 2 (3 bins)
```
Bins: ['BIN_8', 'BIN_10', 'BIN_9']
Internal distances:
  BIN_8 ↔ BIN_10: 674.8m
  BIN_8 ↔ BIN_9: 1018.0m
  BIN_10 ↔ BIN_9: 554.9m
Max internal distance: 1018.0m
```

**Observation**: All clusters have max internal distance < 2000m (the MAX_BIN_RADIUS_M limit).

---

## Distance Calculation

### Haversine Formula
```python
from utils.distance import calculate_distance_km

# Returns distance in kilometers
distance_km = calculate_distance_km(
    {'lat': lat1, 'lng': lng1},
    {'lat': lat2, 'lng': lng2}
)

# Convert to meters
distance_m = distance_km * 1000
```

**Haversine Details**: Accounts for Earth's curvature, accurate for geographic coordinates.

---

## Edge Cases Handled

### 1. Single Bin
```python
# Result: One cluster with single bin
clusters = [[bin]]
```

### 2. No Bins Within Proximity
```python
# Result: Each bin is its own cluster
clusters = [[bin_1], [bin_2], [bin_3], ...]
```

### 3. All Bins in One Cluster
```python
# If all pairwise distances ≤ max radii
clusters = [[bin_1, bin_2, bin_3, ..., bin_n]]
```

### 4. Missing Depots
```python
# Fallback to DEFAULT_BIN_RADIUS_M
if not depots:
    radius = DEFAULT_BIN_RADIUS_M  # 1400m
```

### 5. Chain Clustering
```
BIN_1 ↔ BIN_2 (within radius)
BIN_2 ↔ BIN_3 (within radius)
BIN_1 ↔ BIN_3 (NOT within radius)

Result: All three in same cluster (transitivity via BIN_2)
```

---

## Complexity Analysis

### Time Complexity
- **Radius Calculation**: O(b × d) where b = bins, d = depots
- **Distance Matrix**: O(b²) pairwise distance calculations
- **DFS**: O(b + e) where e = edges in graph
- **Overall**: **O(b² + bd)** ≈ **O(b²)** for typical cases

### Space Complexity
- **Adjacency List**: O(b + e)
- **Visited Set**: O(b)
- **Overall**: **O(b²)** worst case (fully connected graph)

---

## Configuration

### Environment Variables (`.env`)
```bash
DEPOT_DISTANCE_PERCENTAGE=0.35
MAX_BIN_RADIUS_M=2000.0
DEFAULT_BIN_RADIUS_M=1400.0
```

### Loading Configuration
```python
from config.settings import DEPOT_DISTANCE_PERCENTAGE, MAX_BIN_RADIUS_M

# Used in _compute_per_bin_radii()
radius = min_depot_dist * DEPOT_DISTANCE_PERCENTAGE
radius = min(radius, MAX_BIN_RADIUS_M)
```

---

## Usage in Dispatch System

### 1. Cluster Lookup
```python
# When bin reaches threshold, find its cluster
cluster = clustering_service.get_cluster_for_bin(bin_id)
```

### 2. Multi-Bin Collection
```python
# Collect all bins in cluster together
for bin in cluster['bins']:
    if bin['fillLevel'] > threshold * 0.5:  # At least 50% of threshold
        add_to_collection_route(bin)
```

### 3. Duplicate Prevention
```python
# Check if cluster already has assigned truck
if cluster_id in active_cluster_assignments:
    return "wait_for_existing_truck"
```

---

## Design Rationale

### Why Adaptive Radii?
- **Urban Areas** (close to depot): Smaller radii → tighter clusters → shorter routes
- **Rural Areas** (far from depot): Larger radii → broader clusters → reduce depot trips

### Why Max 2000m?
- **Practical Limit**: Beyond 2km, collection efficiency degrades
- **Route Time**: Keeps intra-cluster travel time reasonable
- **Coordination**: Easier to manage smaller geographic areas

### Why 35% of Depot Distance?
- **Empirical Balance**: Tested value that works well for mixed urban/suburban layouts
- **Scalability**: Automatically adjusts to system geography
- **Flexibility**: Configurable via environment variable

---

## Testing Recommendations

### Test Cases
1. ✅ Dense urban layout (small radii, many clusters)
2. ✅ Sparse rural layout (large radii, few clusters)
3. ✅ Mixed density areas
4. ✅ Edge cases: single bin, no proximity, all connected
5. ✅ Chain clustering (transitive connections)

### Validation
```python
# Verify cluster properties
for cluster in clusters:
    assert len(cluster['bins']) > 0
    
    # Check internal distances
    for i, bin_i in enumerate(cluster['bins']):
        for bin_j in cluster['bins'][i+1:]:
            dist = calculate_distance_km(bin_i, bin_j) * 1000
            # At least one path should exist via graph
            assert dist <= MAX_BIN_RADIUS_M * 2  # Upper bound
```

---

## Future Enhancements

### Potential Improvements
1. **K-Means Alternative**: Pre-cluster by k-means, then refine with proximity
2. **Dynamic Reclustering**: Adjust clusters as bins are collected/filled
3. **Capacity-Aware**: Weight clusters by total capacity, not just proximity
4. **Priority Zones**: Different radii for high-priority areas
5. **Historical Learning**: Adjust radii based on past dispatch efficiency

---

## Related Components

### Dependencies
- **Input**: Bins with lat/lng, depots with lat/lng
- **Utilities**: `calculate_distance_km` (Haversine formula)
- **Config**: `.env` variables for radius parameters

### Used By
- **ProactiveClusterDispatchService**: Primary consumer for cluster-scoped dispatch
- **SimulationService**: May use for analytics/visualization
- **Frontend**: Displays clusters on map

---

## Summary

The clustering algorithm is a **proximity-based graph partitioning system** that:
- ✅ Uses adaptive radii based on depot distance (35%)
- ✅ Caps maximum radius at 2000m for practical efficiency
- ✅ Forms clusters via connected components (DFS)
- ✅ Handles transitive proximity (chain clustering)
- ✅ Scales to different geographic layouts (urban/rural)
- ✅ Runs in O(b²) time for typical bin counts

**Key Insight**: Bins closer to depot get smaller radii (tighter clusters), bins farther away get larger radii (broader clusters) up to 2000m limit. This automatically adapts clustering density to system geography.
