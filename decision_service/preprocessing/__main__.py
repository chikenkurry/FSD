"""Run the mock snapshot through preprocessing for local contract review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import preprocess


DEFAULTS = Path(__file__).parents[1] / "fixtures" / "preprocessing"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare DecisionAlgorithmInput from two immutable JSON snapshots")
    parser.add_argument("--planning", type=Path, default=DEFAULTS / "planning_snapshot.json")
    parser.add_argument("--responses", type=Path, default=DEFAULTS / "response_snapshot.json")
    args = parser.parse_args()
    planning = json.loads(args.planning.read_text())
    responses = json.loads(args.responses.read_text())
    print(json.dumps(preprocess(planning, responses), indent=2))


if __name__ == "__main__":
    main()
