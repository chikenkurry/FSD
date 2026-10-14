"""Configure and start Decision's internal HTTP service."""
import os
import logging
import argparse
from pathlib import Path
import re
import shlex
import signal
import threading

from .http_api import DecisionServer
from .store import RunStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    if args.env_file:
        for number, line in enumerate(args.env_file.read_text().splitlines(), 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            match = re.fullmatch(r"\s*([A-Z][A-Z0-9_]*)=(.*)", line)
            if not match:
                raise SystemExit(f"Invalid env assignment at line {number}")
            values = shlex.split(match[2], comments=True)
            if len(values) > 1:
                raise SystemExit(f"Quote the env value at line {number}")
            os.environ.setdefault(match[1], values[0] if values else "")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    token = os.environ.get("INTERNAL_API_TOKEN", "")
    if len(token) < 16:
        raise SystemExit("INTERNAL_API_TOKEN must have at least 16 characters")
    store = RunStore(os.environ.get("DECISION_DB_PATH", "/data/runs.sqlite"))
    provider = None
    mode = os.environ.get("SEMANTIC_PROVIDER", "rules")
    if mode not in {"rules", "ollama"}:
        raise SystemExit("SEMANTIC_PROVIDER must be rules or ollama")
    if mode == "ollama":
        from decision_service.preprocessing.semantics import OllamaSemanticProvider
        provider = OllamaSemanticProvider(model=os.environ.get("OLLAMA_MODEL", "qwen3:4b-instruct"))
    collector = None
    if os.environ.get("GEMINI_API_KEY"):
        from .fact_collection import GeminiFactCollector
        collector = GeminiFactCollector()

    server = DecisionServer(
        ("0.0.0.0", int(os.environ.get("PORT", "8000"))),
        token=token, store=store, semantic_provider=provider,
        planning_url=os.environ["PLANNING_BASE_URL"],
        participation_url=os.environ["PARTICIPATION_BASE_URL"],
        workers=int(os.environ.get("DECISION_WORKERS", "2")),
        fact_collector=collector,
    )
    with server:
        signal.signal(signal.SIGTERM,lambda *_:threading.Thread(target=server.shutdown,daemon=True).start())
        server.serve_forever()


if __name__ == "__main__":
    main()
