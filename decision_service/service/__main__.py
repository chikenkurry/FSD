"""Configure and start Decision's internal HTTP service."""
import os
import logging
import argparse
from pathlib import Path
import re
import shlex
import signal
import threading
from types import SimpleNamespace

from .http_api import DecisionServer
from .store import open_store
from .jobs import JobQueue, JobWorkers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path)
    parser.add_argument('--role', choices=['api', 'worker', 'all', 'migrate', 'retire'], default='all')
    parser.add_argument('--kinds', help='Worker job kinds, separated by commas')
    parser.add_argument('--import-sqlite', type=Path, help='Stopped legacy database, used only with --role migrate')
    parser.add_argument('--implementation-hash', help='Exact retired release hash; --role retire only')
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
    if args.import_sqlite and args.role != 'migrate':
        parser.error('--import-sqlite requires --role migrate')
    if (args.role == 'retire') != bool(args.implementation_hash):
        parser.error('--role retire requires --implementation-hash')
    if args.implementation_hash and not re.fullmatch(r'[0-9a-f]{64}', args.implementation_hash):
        parser.error('Supply the exact 64-character implementation hash')
    if args.kinds and args.role != 'worker':
        parser.error('--kinds is only supported for --role worker')
    if args.role in {'api', 'all'} and any(not os.environ.get(name) for name in ('PLANNING_BASE_URL','PARTICIPATION_BASE_URL')):
        parser.error('API mode requires PLANNING_BASE_URL and PARTICIPATION_BASE_URL')
    store = open_store(migrate=args.role == 'migrate')
    if args.role in {'migrate', 'retire'}:
        try:
            if args.role == 'retire':
                print('Retired jobs:', store.retire_implementation(args.implementation_hash))
            if args.import_sqlite:
                if not store.postgres:
                    raise SystemExit('SQLite import requires DECISION_DATABASE_URL')
                import json
                print(json.dumps(store.import_sqlite(args.import_sqlite)))
        finally:
            store.close()
        return
    token = os.environ.get("INTERNAL_API_TOKEN", "")
    if len(token) < 16:
        raise SystemExit("INTERNAL_API_TOKEN must have at least 16 characters")
    provider = None
    mode = os.environ.get("SEMANTIC_PROVIDER", "rules")
    if mode not in {"rules", "ollama"}:
        raise SystemExit("SEMANTIC_PROVIDER must be rules or ollama")
    if mode == "ollama":
        from decision_service.preprocessing.semantics import OllamaSemanticProvider
        provider = OllamaSemanticProvider(model=os.environ.get("OLLAMA_MODEL", "qwen3:4b-instruct"))
    collector = None
    if args.role == 'api':
        # API version keys match workers without giving the API a provider key.
        collector = SimpleNamespace(provider_name='GeminiFactCollector', model=os.environ.get('GEMINI_FACT_MODEL', 'gemini-3.8-flash'))
    elif os.environ.get("GEMINI_API_KEY"):
        from .fact_collection import GeminiFactCollector
        collector = GeminiFactCollector()

    jobs = JobQueue(store, provider, fact_collector=collector) if args.role == 'api' else JobWorkers(
        store, provider, workers=int(os.environ.get('DECISION_WORKERS', '2')),
        fact_collector=collector, kinds=args.kinds.split(',') if args.kinds else None,
        lease_seconds=int(os.environ.get('DECISION_LEASE_SECONDS', '300')))
    server = DecisionServer(
        ("0.0.0.0", int(os.environ.get("PORT", "8000"))),
        token=token, store=store, semantic_provider=provider,
        planning_url=os.environ.get('PLANNING_BASE_URL', ''),
        participation_url=os.environ.get('PARTICIPATION_BASE_URL', ''),
        jobs=jobs, worker_health=args.role == 'worker',
    )
    try:
        with server:
            def shutdown(*_):
                threading.Thread(target=server.shutdown,daemon=True).start()
            signal.signal(signal.SIGTERM, shutdown)
            signal.signal(signal.SIGINT, shutdown)
            server.serve_forever()
    finally:
        store.close()


if __name__ == "__main__":
    main()
