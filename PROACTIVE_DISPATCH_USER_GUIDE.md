# Proactive Cluster Dispatch System - User Guide

## Overview

The Proactive Cluster Dispatch System is an advanced waste collection optimization feature that prevents redundant truck dispatches when multiple bins in the same geographical cluster reach their disposal threshold (DT) sequentially.

## Problem Solved

**Before**: When multiple bins in the same area reached DT within a short time window, the system would dispatch separate trucks to each bin, leading to:
- Redundant dispatches to the same geographical area
- Inefficient resource utilization  
- Increased operational costs
- Poor capacity utilization

**After**: The system now coordinates dispatches at the cluster level, ensuring:
- Only one truck per cluster when bins reach DT sequentially
- Proactive collection of nearby bins to maximize efficiency
- Intelligent capacity planning and route optimization
- Significant reduction in redundant dispatches

## Key Features

### 1. Enhanced Clustering
- **Geographical Grouping**: Creates logical clusters based on geographical proximity (1200m threshold)
- **Connectivity-Based**: Uses BFS algorithm to ensure all bins in a cluster are properly connected
- **Quality Metrics**: Evaluates cluster quality to ensure optimal grouping

### 2. Proactive Dispatch Coordination
- **Cluster Assignment Tracking**: Maintains state of which clusters have active truck dispatches
- **Redundancy Prevention**: Prevents multiple trucks from being sent to the same cluster
- **Time-Based Coordination**: Tracks dispatch timing to handle sequential DT events

### 3. Capacity Optimization
- **Proactive Collection**: Estimates truck capacity and collects additional bins in the same cluster
- **Knapsack Algorithm**: Optimally selects which bins to collect based on capacity constraints
- **Route Efficiency**: Maximizes collection efficiency within geographical clusters

## API Endpoints

### 1. Handle Bin Reached DT
```http
POST /api/bin_reached_dt
Content-Type: application/json

{
  "bin_id": "bin_north_1",
  "simulation_time": 1000
}
```

**Response**:
```json
{
  "status": "success",
  "dispatch_decision": {
    "action": "dispatch_truck" | "add_to_existing_route",
    "truck_id": "truck_1",
    "bins_to_collect": [...],
    "cluster_id": 0,
    "reason": "First bin in cluster" | "Cluster already has active dispatch"
  }
}
```

### 2. Get Proactive Dispatch Status
```http
GET /api/proactive_dispatch_status
```

**Response**:
```json
{
  "status": "success",
  "proactive_dispatch_status": {
    "proactive_dispatch_enabled": true,
    "active_assignments": {...},
    "collection_queue_size": 5
  }
}
```

## Usage Examples

### Scenario 1: First Bin Reaches DT
```python
# Bin bin_north_1 reaches disposal threshold
result = agent.handle_bin_reached_dt_with_cluster_optimization(
    trigger_bin={"id": "bin_north_1", "fill_level": 85, ...},
    bins=all_bins,
    trucks=available_trucks,
    simulation_time=1000
)

# Expected result:
# {
#   "action": "dispatch_truck",
#   "truck_id": "truck_1", 
#   "bins_to_collect": ["bin_north_1", "bin_north_2"],
#   "reason": "First bin in cluster"
# }
```

### Scenario 2: Second Bin in Same Cluster
```python
# Bin bin_north_3 reaches DT 30 seconds later (same cluster)
result = agent.handle_bin_reached_dt_with_cluster_optimization(
    trigger_bin={"id": "bin_north_3", "fill_level": 82, ...},
    bins=all_bins,
    trucks=available_trucks,
    simulation_time=1030
)

# Expected result:
# {
#   "action": "add_to_existing_route",
#   "reason": "Cluster already has active dispatch",
#   "existing_truck": "truck_1"
# }
```

## Configuration

### Clustering Parameters
```python
# In clustering_service.py
self.optimal_distance_threshold = 1200  # Meters - distance for cluster grouping
self.min_cluster_size = 1               # Minimum bins per cluster
self.max_cluster_size = 10              # Maximum bins per cluster
```

### Proactive Dispatch Parameters
```python
# In proactive_cluster_dispatch_service.py
self.dispatch_timeout = 1800            # Seconds - how long dispatch assignment lasts
self.capacity_safety_margin = 0.95      # Use 95% of truck capacity for safety
self.proactive_threshold_buffer = 5     # Collect bins within 5% of DT
```

## Performance Metrics

### Before Implementation
- **Clusters Created**: 10 fragmented clusters from 10 bins
- **Redundant Dispatches**: High frequency when multiple bins reach DT
- **Capacity Utilization**: Sub-optimal due to single-bin collection trips

### After Implementation  
- **Clusters Created**: 3 logical geographical clusters from 10 bins (70% reduction)
- **Redundant Dispatches**: Eliminated through cluster-aware coordination
- **Capacity Utilization**: Improved through proactive bin collection

## Testing

### Simple Logic Test
```bash
cd /path/to/Cleanify
python3 test_simple_proactive_dispatch.py
```

### Enhanced Clustering Test
```bash
cd /path/to/Cleanify/cleanify/simulation-backend
python3 ../../test_enhanced_clustering.py
```

### Integration Test
```bash
cd /path/to/Cleanify/cleanify/simulation-backend  
python3 ../../test_final_integration.py
```

## Troubleshooting

### Common Issues

1. **Clusters Not Forming Properly**
   - Check distance threshold in `clustering_service.py`
   - Verify bin coordinates are correct
   - Ensure connectivity algorithm is working

2. **Redundant Dispatches Still Occurring**
   - Check cluster assignment tracking in `proactive_cluster_dispatch_service.py`
   - Verify time-based coordination logic
   - Ensure API endpoints are using the new methods

3. **Capacity Estimation Issues**
   - Check truck capacity values
   - Verify bin fill level calculations
   - Ensure knapsack algorithm parameters are correct

### Debug Information

Enable debug logging to track dispatch decisions:
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# This will show detailed information about:
# - Cluster formation
# - Dispatch decision logic
# - Capacity calculations
# - Assignment tracking
```

## Future Enhancements

1. **Dynamic Clustering**: Adjust cluster boundaries based on traffic conditions
2. **Predictive Dispatch**: Use ML to predict when bins will reach DT
3. **Multi-Objective Optimization**: Balance dispatch efficiency with environmental impact
4. **Real-Time Adaptation**: Adjust strategies based on real-time operational data

## Support

For issues or questions regarding the Proactive Cluster Dispatch System:
1. Check the test files for working examples
2. Review the implementation summary document
3. Examine the debug logs for detailed execution traces
4. Refer to the API documentation for correct usage patterns