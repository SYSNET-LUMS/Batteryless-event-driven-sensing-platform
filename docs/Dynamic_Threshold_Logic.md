# Dynamic Threshold Calculation Logic

## Overview
The dynamic threshold system determines when a bin needs collection based on its fill level, capacity, and fill rate. This prevents both overflow and inefficient early collections.

## Location
**File**: `cleanify/simulation-backend/src/services/simulation/simulation_service.py`  
**Method**: `SimulationService._calculate_single_dynamic_threshold()`

---

## Core Formula

```
threshold = 100 × (1 - (fillRate × T_min / capacity))
```

Where:
- **fillRate**: Rate at which bin fills (liters/hour)
- **T_min**: Minimum time window for collection (default: 24 hours)
- **capacity**: Maximum bin capacity (liters)

---

## Step-by-Step Calculation

### 1. **Extract Bin Parameters**
```python
fill_rate = bin_data.get('fillRate', 0)  # L/h
capacity = bin_data.get('capacity', 100)  # L
```

### 2. **Apply Fill Rate Safety**
```python
# If fill rate is extremely low, cap threshold at 95%
if fill_rate < 0.01:
    return 95.0
```

### 3. **Calculate Raw Threshold**
```python
T_min = 24.0  # hours (minimum collection window)
raw_threshold = 100 * (1 - (fill_rate * T_min / capacity))
```

**Interpretation**: 
- High fill rate → Lower threshold (collect earlier)
- Low fill rate → Higher threshold (wait longer)

### 4. **Apply Bounds Clamping**
```python
threshold = max(50.0, min(95.0, raw_threshold))
```
- **Minimum**: 50% (prevents too-early collection)
- **Maximum**: 95% (safety margin to prevent overflow)

### 5. **Return Final Threshold**
```python
return round(threshold, 2)
```

---

## Examples

### Example 1: High Fill Rate Bin
- **Capacity**: 500L
- **Fill Rate**: 15 L/h
- **Calculation**:
  ```
  raw_threshold = 100 × (1 - (15 × 24 / 500))
                = 100 × (1 - 0.72)
                = 28.0
  clamped = max(50, min(95, 28.0)) = 50.0
  ```
- **Result**: **50%** (minimum threshold - collect when half full due to rapid filling)

### Example 2: Low Fill Rate Bin
- **Capacity**: 500L
- **Fill Rate**: 2 L/h
- **Calculation**:
  ```
  raw_threshold = 100 × (1 - (2 × 24 / 500))
                = 100 × (1 - 0.096)
                = 90.4
  clamped = max(50, min(95, 90.4)) = 90.4
  ```
- **Result**: **90.4%** (can wait longer before collection)

### Example 3: Very Low Fill Rate
- **Capacity**: 500L
- **Fill Rate**: 0.005 L/h
- **Early Exit**: fillRate < 0.01
- **Result**: **95%** (maximum threshold)

### Example 4: Medium Fill Rate
- **Capacity**: 1000L
- **Fill Rate**: 10 L/h
- **Calculation**:
  ```
  raw_threshold = 100 × (1 - (10 × 24 / 1000))
                = 100 × (1 - 0.24)
                = 76.0
  clamped = max(50, min(95, 76.0)) = 76.0
  ```
- **Result**: **76%**

---

## Edge Cases Handled

### 1. **Negative or Zero Fill Rate**
```python
if fill_rate <= 0:
    return 95.0  # Maximum threshold (static bin)
```

### 2. **Extremely Low Fill Rate**
```python
if fill_rate < 0.01:
    return 95.0  # Avoid division issues
```

### 3. **Very High Fill Rate**
- If calculated threshold < 50%, clamped to 50%
- Prevents premature collection at very low fill levels

### 4. **Overflow Risk**
- Maximum threshold of 95% provides 5% safety buffer
- Even slow-filling bins won't reach 100%

---

## Configuration Constants

| Parameter | Default Value | Source | Description |
|-----------|---------------|---------|-------------|
| `T_min` | 24.0 hours | Hardcoded in method | Minimum time window for collection |
| `MIN_THRESHOLD` | 50.0% | Hardcoded | Lower bound (prevent early collection) |
| `MAX_THRESHOLD` | 95.0% | Hardcoded | Upper bound (safety margin) |
| `FILL_RATE_EPSILON` | 0.01 L/h | Hardcoded | Minimum fill rate threshold |

---

## Usage in Simulation

### When Threshold is Calculated
1. **System initialization**: For each bin in saved system
2. **Real-time updates**: When bin fill rate changes
3. **Agent decisions**: Referenced by `DecisionService` and `ProactiveClusterDispatchService`

### Dispatch Trigger
```python
if bin['fillLevel'] >= bin['dynamicThreshold']:
    # Trigger collection logic
    dispatch_truck_to_bin(bin)
```

---

## Design Rationale

### Why This Formula?
1. **Time-Based Safety**: Ensures bins won't overflow within next 24 hours
2. **Adaptive**: Automatically adjusts to different fill rates
3. **Resource Efficient**: High-threshold bins require fewer trips
4. **Overflow Prevention**: 95% cap provides safety buffer

### Why These Bounds?
- **50% minimum**: Prevents inefficient trips for nearly-empty bins
- **95% maximum**: Accounts for fill rate fluctuations and collection delays

---

## Related Components

### Dependencies
- **Input**: Bin data with `fillRate`, `capacity`, `fillLevel`
- **Called By**: `SimulationService.update_bin()`, agent initialization

### Downstream Impact
- **DecisionService**: Uses threshold to decide dispatch timing
- **ProactiveClusterDispatchService**: Triggers cluster-wide collection
- **TrafficManager**: Considers threshold in wait-vs-dispatch decisions

---

## Testing Recommendations

### Test Cases
1. ✅ Low fill rate (< 0.01 L/h) → Should return 95%
2. ✅ High fill rate (> capacity/T_min) → Should return 50%
3. ✅ Medium fill rate → Should return value between bounds
4. ✅ Zero/negative fill rate → Should return 95%
5. ✅ Edge case: fillRate × T_min = capacity → Should return 50%

### Validation
```python
# Example test
bin = {'fillRate': 5.0, 'capacity': 200}
threshold = service._calculate_single_dynamic_threshold(bin)
assert 50.0 <= threshold <= 95.0
```

---

## Future Enhancements

### Potential Improvements
1. **Configurable T_min**: Allow per-bin or system-wide adjustment
2. **Multi-horizon**: Different thresholds for different time windows
3. **Historical Learning**: Adjust based on past fill rate patterns
4. **Priority Tiers**: Different bounds for high-priority bins
5. **Seasonal Adjustment**: Account for predictable fill rate changes

---

## Summary

The dynamic threshold calculation is a **time-based safety mechanism** that:
- ✅ Adapts to each bin's fill rate
- ✅ Prevents overflow (95% max)
- ✅ Avoids premature collection (50% min)
- ✅ Provides 24-hour safety window
- ✅ Handles edge cases gracefully

**Key Insight**: The threshold is inversely proportional to fill rate - faster-filling bins get lower thresholds (collect earlier), slower-filling bins get higher thresholds (wait longer).
