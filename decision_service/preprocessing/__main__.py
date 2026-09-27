"""Run the mock snapshot through preprocessing for local contract review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import preprocess
from .semantics import OpenAISemanticProvider, SemanticServiceError


DEFAULTS = Path(__file__).parents[1] / "fixtures" / "preprocessing"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare DecisionAlgorithmInput from two immutable JSON snapshots")
    parser.add_argument("--planning", type=Path, default=DEFAULTS / "planning_snapshot.json")
    parser.add_argument("--responses", type=Path, default=DEFAULTS / "response_snapshot.json")
    parser.add_argument("--semantic-provider", choices=["rules", "openai"], default="rules")
    parser.add_argument("--model", default="gpt-6-astra", help="OpenAI model used only with --semantic-provider openai")
    parser.add_argument("--semantic-evidence", type=Path, help="Previously accepted model assessments to replay without a model call")
    args = parser.parse_args()
    planning = json.loads(args.planning.read_text())
    responses = json.loads(args.responses.read_text())
    evidence = json.loads(args.semantic_evidence.read_text()) if args.semantic_evidence else None
    try:
        provider = OpenAISemanticProvider(model=args.model) if args.semantic_provider == "openai" else None
    except SemanticServiceError as exc:
        parser.error(str(exc))
    print(json.dumps(preprocess(planning, responses, semantic_provider=provider, semantic_evidence=evidence), indent=2))


if __name__ == "__main__":
    main()
