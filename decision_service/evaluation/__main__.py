"""Command-line evaluation using rules, a configured provider, or saved evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from decision_service.preprocessing.semantics import (
    OllamaSemanticProvider, OpenAISemanticProvider, SemanticServiceError,
)

from .runner import evaluate, load_dataset


DEFAULT_DATASET = Path(__file__).parents[1] / "fixtures" / "evaluation" / "cases.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate preprocessing against labelled snapshots")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--semantic-provider", choices=["rules", "ollama", "openai"], default="rules")
    parser.add_argument("--model", help="Override the existing provider's default model")
    parser.add_argument("--ollama-url", help="Existing Ollama server URL")
    parser.add_argument("--evidence-dir", type=Path, help="Replay one saved case_id.json file per selected case")
    parser.add_argument("--save-evidence-dir", type=Path, help="Save accepted model evidence for later replay")
    parser.add_argument("--tag", action="append", default=[], help="Select cases with every specified tag")
    parser.add_argument("--output", type=Path, help="Write the JSON report to this file instead of stdout")
    args = parser.parse_args()
    if args.evidence_dir and args.semantic_provider != "rules":
        parser.error("--evidence-dir cannot be combined with a live provider")
    if args.semantic_provider == "rules" and (args.model or args.ollama_url):
        parser.error("Model and server overrides require a live provider")
    if args.ollama_url and args.semantic_provider != "ollama":
        parser.error("--ollama-url requires --semantic-provider ollama")
    try:
        dataset = load_dataset(args.dataset)
        if args.semantic_provider == "ollama":
            provider = OllamaSemanticProvider(**({"model": args.model} if args.model else {}), base_url=args.ollama_url)
        elif args.semantic_provider == "openai":
            provider = OpenAISemanticProvider(**({"model": args.model} if args.model else {}))
        else:
            provider = None
        report = evaluate(
            dataset, semantic_provider=provider, evidence_dir=args.evidence_dir,
            save_evidence_dir=args.save_evidence_dir, tags=tuple(args.tag),
            progress=lambda number, total, case_id: print(f"[{number}/{total}] {case_id}", file=sys.stderr, flush=True),
        )
        rendered = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (OSError, ValueError, SemanticServiceError) as exc:
        parser.error(str(exc))
    print(f"Cases: {report['cases']['passed']}/{report['cases']['total']}; "
          f"assertions: {report['assertions']['passed']}/{report['assertions']['total']}; "
          f"operational errors: {report['operational_errors']}", file=sys.stderr)
    return 0 if report["cases"]["passed"] == report["cases"]["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
