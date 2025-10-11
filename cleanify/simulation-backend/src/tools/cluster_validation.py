#!/usr/bin/env python3
"""
Validate clustering across all saved system files.
Scans both simulation-backend/saved_systems and src/saved_systems (if present),
loads each system file, computes clusters using ClusteringService with per-bin radii,
and prints a concise summary.

Run: python -m tools.cluster_validation
"""
import os
import json
from typing import List, Dict

try:
    # Relative import when run as module
    from services.clustering_service import ClusteringService
except Exception:
    # Fallback path adjustment for direct execution
    import sys
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    SRC_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
    if SRC_DIR not in sys.path:
        sys.path.insert(0, SRC_DIR)
    from services.clustering_service import ClusteringService


def _summarize_clusters(clusters: Dict) -> Dict:
    sizes = [len(bins) for bins in clusters.values()] if clusters else []
    total_bins = sum(sizes)
    return {
        "clusters": len(sizes),
        "total_bins": total_bins,
        "avg_size": round(total_bins / len(sizes), 2) if sizes else 0,
        "max_size": max(sizes) if sizes else 0,
        "singletons": sum(1 for s in sizes if s == 1),
    }


def _find_saved_dirs() -> List[str]:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.abspath(os.path.join(current_dir, ".."))
    root_dir = os.path.abspath(os.path.join(src_dir, ".."))
    candidates = [
        os.path.join(root_dir, "saved_systems"),           # simulation-backend/saved_systems
        os.path.join(src_dir, "saved_systems"),            # simulation-backend/src/saved_systems
    ]
    return [d for d in candidates if os.path.isdir(d)]


def main():
    saved_dirs = _find_saved_dirs()
    if not saved_dirs:
        print("No saved_systems directories found.")
        return

    cs = ClusteringService()
    total_files = 0
    errors = 0

    for d in saved_dirs:
        print(f"\nScanning: {d}")
        for name in sorted(os.listdir(d)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(d, name)
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                bins = data.get("bins", [])
                depots = data.get("depots", [])
                clusters = cs.create_simple_dynamic_clusters(bins, depots)
                summary = _summarize_clusters(clusters)
                print(f"- {name}: bins={len(bins)}, depots={len(depots)}, "
                      f"clusters={summary['clusters']}, avg={summary['avg_size']}, "
                      f"max={summary['max_size']}, singletons={summary['singletons']}")
                total_files += 1
            except Exception as e:
                print(f"! {name}: ERROR {e}")
                errors += 1

    print(f"\nDone. Files processed: {total_files}, errors: {errors}")


if __name__ == "__main__":
    main()
