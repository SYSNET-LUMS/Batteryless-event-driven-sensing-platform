#!/usr/bin/env python3
"""CLI utility to collect OSRM, VROOM, and distance cache health metrics."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from api.app import create_app  # type: ignore  # noqa: E402
from services.health.service_health import ServiceHealthReporter  # type: ignore  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect OSRM/VROOM/cache health metrics via ServiceHealthReporter",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="How many forced cache rebuilds to run for performance sampling",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the JSON results",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON for readability",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = create_app()

    with app.app_context():
        reporter = ServiceHealthReporter(
            app.osrm_service,
            app.vroom_service,
            app.distance_matrix_service,
        )
        report = reporter.collect(
            bins=app.system_repository.get_bins(),
            depots=app.system_repository.get_depots(),
            iterations=max(1, args.iterations),
        )

    json_kwargs: Dict[str, Any] = {"indent": 2} if args.pretty else {}
    payload = json.dumps(report, **json_kwargs)
    print(payload)

    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"📄 Wrote results to {args.output}")


if __name__ == "__main__":
    main()
