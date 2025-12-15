"""Dynamic threshold (DT) calculation for bins."""
from __future__ import annotations

from typing import Dict, Iterable, Optional


class DynamicThresholdService:
    """Calculates adaptive bin thresholds based on fill rate and capacity."""

    MIN_THRESHOLD = 50.0
    MAX_THRESHOLD = 95.0
    FILL_RATE_EPSILON = 0.01

    def __init__(self, t_min_hours: float = 24.0) -> None:
        self.t_min_hours = max(1.0, float(t_min_hours))

    def calculate_threshold(self, bin_data: Dict) -> float:
        """Return the DT for a single bin following the provided formula."""
        fill_rate = self._as_float(bin_data.get('fillRate') or bin_data.get('fill_rate'))
        capacity = self._as_float(bin_data.get('capacity'))

        if capacity <= 0:
            capacity = 500.0  # fallback to default capacity

        if fill_rate <= 0 or fill_rate < self.FILL_RATE_EPSILON:
            return self.MAX_THRESHOLD

        raw_threshold = 100.0 * (1.0 - (fill_rate * self.t_min_hours / capacity))
        clamped = max(self.MIN_THRESHOLD, min(self.MAX_THRESHOLD, raw_threshold))
        return round(clamped, 2)

    def apply_to_bins(self, bins: Optional[Iterable[Dict]]) -> None:
        """Annotate each bin dict with a ``dynamic_threshold`` value."""
        if not bins:
            return
        for bin_data in bins:
            if not isinstance(bin_data, dict):
                continue
            bin_data['dynamic_threshold'] = self.calculate_threshold(bin_data)

    @staticmethod
    def _as_float(value: Optional[float]) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
