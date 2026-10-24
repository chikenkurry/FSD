"""Run the mock snapshot through preprocessing for local contract review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import preprocess
from .semantics import OllamaSemanticProvider, OpenAISemanticProvider, SemanticServiceError


DEFAULTS = Path(__file__).parents[1] / "fixtures" / "preprocessing"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare DecisionAlgorithmInput from two immutable JSON snapshots")
    parser.add_argument("--planning", type=Path, default=DEFAULTS / "planning_snapshot.json")
    parser.add_argument("--responses", type=Path, default=DEFAULTS / "response_snapshot.json")
    parser.add_argument("--semantic-provider", choices=["rules", "ollama", "openai"], default="rules")
    parser.add_argument("--model", help="Model name; defaults to qwen3:4b-instruct for Ollama")
    parser.add_argument("--ollama-url", help="Ollama server URL (default: OLLAMA_BASE_URL or http://localhost:11434)")
    parser.add_argument("--semantic-evidence", type=Path, help="Previously accepted model assessments to replay without a model call")
    args = parser.parse_args()
    planning = json.loads(args.planning.read_text())
    responses = json.loads(args.responses.read_text())
    evidence = json.loads(args.semantic_evidence.read_text()) if args.semantic_evidence else None
    try:
        if args.semantic_provider == "ollama":
            provider = OllamaSemanticProvider(model=args.model or "qwen3:4b-instruct", base_url=args.ollama_url)
        elif args.semantic_provider == "openai":
            provider = OpenAISemanticProvider(model=args.model or "gpt-6-astra")
        else:
            provider = None
    except SemanticServiceError as exc:
        parser.error(str(exc))
    print(json.dumps(preprocess(planning, responses, semantic_provider=provider, semantic_evidence=evidence), indent=2))


if __name__ == "__main__":
    main()
