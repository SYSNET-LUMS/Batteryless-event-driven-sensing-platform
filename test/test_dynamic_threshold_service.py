import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "cleanify" / "simulation-backend" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from services.dynamic_threshold_service import DynamicThresholdService  # type: ignore  # noqa: E402


def test_high_fill_rate_clamped_to_min_threshold():
    service = DynamicThresholdService()
    bin_data = {"fillRate": 15.0, "capacity": 500.0}
    assert service.calculate_threshold(bin_data) == 50.0


def test_low_fill_rate_returns_expected_value():
    service = DynamicThresholdService()
    bin_data = {"fillRate": 2.0, "capacity": 500.0}
    assert service.calculate_threshold(bin_data) == 90.4


def test_extremely_low_fill_rate_caps_at_95():
    service = DynamicThresholdService()
    bin_data = {"fillRate": 0.005, "capacity": 500.0}
    assert service.calculate_threshold(bin_data) == 95.0


def test_negative_or_zero_fill_rate_caps_at_95():
    service = DynamicThresholdService()
    assert service.calculate_threshold({"fillRate": 0, "capacity": 500.0}) == 95.0
    assert service.calculate_threshold({"fillRate": -2, "capacity": 800.0}) == 95.0
