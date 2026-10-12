"""Internal HTTP API; public recommendation access is authorised by Planning."""
import hmac
import json
import logging
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from decision_service.preprocessing.common import InputError
from .snapshots import SnapshotError, validate_planning_snapshot
from .store import RunStore
from .workflow import execute
from .views import member_review, public_result


class UpstreamError(Exception):
    pass


def read_snapshot(base: str, path: str, token: str) -> dict:
    request = Request(base.rstrip('/') + path, headers={"x-internal-token": token})
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read(2_000_001))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise UpstreamError("Snapshot service unavailable") from exc


class DecisionServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], *, token: str, store: RunStore,
                 planning_url: str, participation_url: str, semantic_provider=None):
        self.token = token
        self.store = store
        self.planning_url = planning_url
        self.participation_url = participation_url
        self.semantic_provider = semantic_provider
        super().__init__(address, DecisionHandler)


class DecisionHandler(BaseHTTPRequestHandler):
    server: DecisionServer

    def log_message(self, *args):
        pass  # Never log credentials, raw answers or private run bodies.

    def send_json(self, status, payload):
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        if self.path == "/health" and self.command == "GET":
            return self.send_json(200, {"status": "ok"})
        if not hmac.compare_digest(self.headers.get("x-internal-token", ""), self.server.token):
            return self.send_json(401, {"code": "UNAUTHENTICATED"})
        try:
            body = {}
            if self.command == "POST":
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 2_000_000:
                    return self.send_json(413, {"code": "INVALID_INPUT"})
                body = json.loads(self.rfile.read(length) or b'{}')
                if not isinstance(body, dict):
                    raise SnapshotError("Body must be an object")
            self.dispatch(body)
        except (SnapshotError, InputError, ValueError, TypeError) as exc:
            self.send_json(400, {"code": "INVALID_INPUT", "message": str(exc)})
        except UpstreamError:
            self.send_json(503, {"code": "UPSTREAM_UNAVAILABLE", "retryable": True})
        except Exception as error:
            frames = [(frame.name, frame.lineno) for frame in traceback.extract_tb(error.__traceback__)]
            logging.error("Internal failure %s at %s", type(error).__name__, frames)
            self.send_json(500, {"code": "INTERNAL", "retryable": True})

    def dispatch(self, body: dict) -> None:
        parts = self.path.strip('/').split('/')
        if self.path == "/internal/planning/validate" and self.command == "POST":
            validate_planning_snapshot(body)
            return self.send_json(200, {"status": "valid"})
        if len(parts) == 4 and parts[:2] == ["internal", "rounds"] and parts[3] == "recommendations" and self.command == "POST":
            return self.recommend(str(UUID(parts[2])))
        if len(parts) in {3, 4, 5} and parts[:2] == ["internal", "runs"]:
            run = self.server.store.get(str(UUID(parts[2])))
            if not run:
                return self.send_json(404, {"code": "NOT_FOUND"})
            if len(parts) == 3 and self.command == "GET":
                return self.send_json(200, public_result(run))
            if len(parts) == 5 and parts[3] == "clarifications" and self.command == "GET":
                member_id = str(UUID(parts[4]))
                members = set(run.get("member_states", {}))
                if member_id not in members:
                    return self.send_json(403, {"code": "FORBIDDEN"})
                return self.send_json(200, member_review(run, member_id))
            if len(parts) == 4 and parts[3] == "validate-selection" and self.command == "POST":
                return self.validate_selection(run, body)
        self.send_json(404, {"code": "NOT_FOUND"})

    def recommend(self, round_id: str) -> None:
        planning = read_snapshot(self.server.planning_url, f"/internal/rounds/{round_id}/option-snapshot", self.server.token)
        responses = read_snapshot(self.server.participation_url, f"/internal/rounds/{round_id}/response-snapshot", self.server.token)
        run = self.server.store.save(execute(planning, responses, semantic_provider=self.server.semantic_provider), planning, responses)
        return self.send_json(200, public_result(run))

    def validate_selection(self, run: dict, body: dict) -> None:
        if body.get("input_refs") != run["input_refs"] or run["status"] != "ranked":
            return self.send_json(409, {"code": "STALE_OR_BLOCKED_RESULT"})
        rows = run["result"].get("ranked_candidates", [])
        key = "option_id" if run["algorithm_input"]["context"]["schema_version"] == "generic-option-v1" else "candidate_id"
        if not any(row[key] == body.get("candidate_id") for row in rows):
            return self.send_json(409, {"code": "INELIGIBLE_CANDIDATE"})
        return self.send_json(200, {"run_id": run["run_id"], "candidate_id": body["candidate_id"], "input_refs": run["input_refs"]})
