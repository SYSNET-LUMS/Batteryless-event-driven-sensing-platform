# Analysis — Depth & Ultrasonic Sensor Characterization

Complete analysis pipeline for RealSense depth camera characterization and HC-SR04 ultrasonic sensor validation across 50 field deployment runs.

## Overview

This folder contains the full analysis workflow for the Batteryless Event-Driven Sensing Platform's bin fill-level sensing system. The system combines:
- **RealSense D455** depth camera for ground truth fill-level measurement
- **HC-SR04** ultrasonic ranging sensor for deployment use
- **50 validation runs** across real-world field conditions

## Folder Structure

```
analysis/
├── README.md (this file)
├── rectangle_coordinates.json       # ROI definitions for all 50 runs
│
├── notebooks/
│   └── depth_3d_analysis_50runs.ipynb     # Main analysis notebook
│                                           # - Processes all 50 ROS bag files
│                                           # - Extracts RealSense depth/RGB frames
│                                           # - Generates 2D & 3D visualizations
│
├── raw_runs/                        # Raw sensor data (ROS bag format)
│   ├── run1.bag through run50.bag   # 50 bags, ~11 GB total
│   │                                # Each contains:
│   │                                # - RealSense D455 depth (640×480 @30fps, 16-bit)
│   │                                # - Synchronized RGB frames (640×480 @30fps)
│   │                                # - Camera intrinsics & timestamps
│   └── ...
│
├── baseline_ultrasonic/             # HC-SR04 sensor calibration
│   └── baseline_ultrasonic_values.txt       # Original measurement file
│
├── Images/                          # Averaged sensor frames (50 runs)
│   ├── run1_rgb_avg.png through run50_rgb_avg.png      (RGB averages)
│   └── run1_depth_avg.png through run50_depth_avg.png  (Depth averages)
│
├── Wall Masks/                      # Wall exclusion masks (50 runs)
│   ├── run1_depth_avg.png through run50_depth_avg.png
│   │                                # Binary masks for interior vs wall regions
│   │                                # Used to exclude container walls from analysis
│   └── ...
│
└── results/
    └── run_outputs/                 # Output visualizations (50 runs)
        ├── run1_output_1.png through run50_output_1.png
        │                            # 2D matplotlib figures showing:
        │                            # - Left: Depth heatmap (viridis colormap)
        │                            # - Right: RGB ROI image
        │                            # ~200-450 KB each, ready for reports
        └── ...
```

## Data Formats

### ROS Bag Files (raw_runs/)
Binary ROS message format containing timestamped sensor data. Extract with:
```bash
rosbag info analysis/raw_runs/run1.bag
rosbag play analysis/raw_runs/run1.bag
```

### ROI Coordinates (rectangle_coordinates.json)
Region-of-Interest definitions for depth and RGB crops per run:
```json
{
  "run1": {
    "depth": [x1, y1, x2, y2],    // RealSense depth ROI (pixel coords)
    "rgb": [x1, y1, x2, y2]       // RealSense RGB ROI (pixel coords)
  }
}
```

### Output Images (run_outputs/)
PNG files from notebook 2D plot outputs. Two per run:
- `run1_output_1.png`: 2D depth map + RGB ROI side-by-side
  - Shows processed depth with wall exclusion applied
  - Includes depth colorbar (0–563.2 mm range)

### Ultrasonic Calibration (baseline_ultrasonic/)

**ultrasonic_vs_ground_truth.csv** — 15-run validation:
```
Run,Ground_Truth_mm,Ultrasonic_Raw_mm,Ultrasonic_Bias_Corrected_mm,Error_mm,Abs_Error_mm
run1,154.5,166.7,173.4,18.9,18.9
run2,122.4,144.4,151.1,28.7,28.7
...
```

**Accuracy Summary:**
- Median Absolute Error: **31.5 mm**
- Mean Absolute Error: **49.9 mm**
- Systematic Bias: **-6.7 mm** (subtract from raw readings)
- Range of depths covered: 107.3–419.4 mm (ground truth)

## Analysis Notebook

### File
`notebooks/depth_3d_analysis_50runs.ipynb`

### Contents
1. **Setup (Cells 0–4)**
   - Imports & configuration
   - Load ultrasonic baseline values (all 50 runs)
   - Load ROI coordinates from JSON
   - Helper function definitions

2. **Per-Run Analysis (Cells 5–107)**
   - 50 sections (one per run)
   - Each section:
     - Loads .bag file
     - Extracts depth frames via pyrealsense2
     - Computes average depth
     - Crops to ROI, filters invalid ranges (600–2000 mm)
     - Applies wall exclusion mask
     - Generates 2D matplotlib figure (depth + RGB)
     - Generates interactive 3D plotly surface
     - Outputs fill-level estimate and error metrics

3. **Wall Exclusion Algorithm**
   - Loads pre-computed wall masks from `Wall Masks/`
   - Binary mask: 1 = interior (include), 0 = wall (exclude)
   - Reduces outlier spikes from container walls

4. **Output Visualization**
   - 2D plot: Depth heatmap + RGB ROI
   - 3D plot: Interactive surface with reference planes
     - Viridis colormap for depth
     - Crimson plane: ultrasonic reading (if available)
     - Orange plane: depth map average (ground truth)

## Key Measurements

### Per-Run Base Depths
- **Group A (run1–15):** 676 mm
- **Group B (run16):** 731 mm
- **Group C (run17–50):** 780 mm

These constants are used to convert fill-level readings (in cm) to absolute depth.

### Ultrasonic Readings
All 50 runs stored in ULTRASONIC_CM dict within notebook:
```python
ULTRASONIC_CM = {
    'run1': 12.95,  'run2': 10.75, ...  'run50': 4.9
}
```

## Workflow

```
raw_runs/ .bag files
    ↓
[Extract depth + RGB frames with pyrealsense2]
    ↓
[Crop to ROI using rectangle_coordinates.json]
    ↓
[Filter invalid depth range (600–2000 mm)]
    ↓
[Apply wall exclusion masks from Wall Masks/]
    ↓
[Compute average depth within interior region]
    ↓
[Generate depth map image]
    ↓
[Output: PNG + 3D visualization]
    ↓
results/run_outputs/
```

