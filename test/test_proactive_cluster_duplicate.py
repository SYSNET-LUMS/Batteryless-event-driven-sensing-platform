import json
import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "cleanify" / "simulation-backend" / "src")
)

from services.agent_service import WasteCollectionAgent  # noqa: E402

SYSTEM_PATH = Path(
    "/media/muneeb-ur-rehman/CA66F1CB66F1B871/Study/Sproj/Cleanify/cleanify/"
    "simulation-backend/saved_systems/cleanify_system_20251007_130200.json"
)


def _load_agent():
    agent = WasteCollectionAgent()
    with SYSTEM_PATH.open() as fh:
        data = json.load(fh)
    agent.bins_data = data["bins"]
    agent.depot_data = data.get("depots", [])
    agent.trucks_data = data.get("trucks", [])
    agent.collection_queue = []
    return agent


def _set_fill(agent, bin_id: str, fill: float) -> None:
    for bin_data in agent.bins_data:
        if bin_data.get("id") == bin_id:
            bin_data["fillLevel"] = fill
            break


def test_cluster_dispatch_does_not_duplicate_trucks():
    agent = _load_agent()

    _set_fill(agent, "BIN_5", 85)
    _set_fill(agent, "BIN_7", 78)
    _set_fill(agent, "BIN_6", 76)

    bins = agent.bins_data
    trucks = agent.trucks_data

    first = agent.handle_bin_reached_dt_with_cluster_optimization(
        next(b for b in bins if b["id"] == "BIN_5"), bins, trucks, 0.0
    )

    assert first["dispatch_recommendation"] == "dispatch"
    assert first["proactive_bins_added"] == 2
    assigned_truck = first["assigned_truck_id"]
    assert assigned_truck

    _set_fill(agent, "BIN_7", 82)

    second = agent.handle_bin_reached_dt_with_cluster_optimization(
        next(b for b in bins if b["id"] == "BIN_7"), bins, trucks, 60.0
    )

    assert second["dispatch_recommendation"] == "wait_for_existing_truck"
    assert second["assigned_truck_id"] == assigned_truck
    assignments = agent.proactive_dispatch.get_active_assignments()
    matching_keys = [
        cid
        for cid, info in assignments.items()
        if set(info["assigned_bins"]) == {"BIN_5", "BIN_6", "BIN_7"}
    ]
    assert matching_keys, "expected cluster assignment to remain active"
    assignment = assignments[matching_keys[0]]
    assert assignment["truck_id"] == assigned_truck
    truck_capacity = next(
        truck["capacity"] for truck in agent.trucks_data if truck["id"] == assigned_truck
    )
    assert assignment["total_load"] <= truck_capacity
