"""Configure and start Decision's internal HTTP service."""
import os

from .http_api import DecisionServer
from .store import RunStore


def main():
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

    server = DecisionServer(
        ("0.0.0.0", int(os.environ.get("PORT", "8000"))),
        token=token, store=store, semantic_provider=provider,
        planning_url=os.environ["PLANNING_BASE_URL"],
        participation_url=os.environ["PARTICIPATION_BASE_URL"],
    )
    with server:
        server.serve_forever()


if __name__ == "__main__":
    main()
