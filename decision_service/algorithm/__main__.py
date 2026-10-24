from __future__ import annotations

import argparse
import json
from pathlib import Path

from .run import run_decision


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the What2Do decision algorithm")
    parser.add_argument("algorithm_input", type=Path, help="JSON file containing the processed algorithm_input object")
    parser.add_argument("--run-id", default="manual-run")
    args = parser.parse_args()

    data = json.loads(args.algorithm_input.read_text(encoding="utf-8"))
    result = run_decision(data, run_id=args.run_id)
    print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
