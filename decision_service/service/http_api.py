"""Internal HTTP API; public access and member identity are owned by Planning."""
from copy import deepcopy
import hmac
import json
import logging
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from decision_service.preprocessing.common import InputError
from .jobs import JobWorkers
from .snapshots import SnapshotError, validate_planning_snapshot, inspect_definition
from .store import RunStore, QueueFull
from .views import member_review, public_result

MAX_BODY = 2_000_000
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class UpstreamError(Exception):
    pass


def read_snapshot(base: str, path: str, token: str, request_id: str = "") -> dict:
    request = Request(base.rstrip('/') + path, headers={"x-internal-token": token, "x-request-id": request_id})
    try:
        with urlopen(request, timeout=10) as response:
            payload = response.read(MAX_BODY + 1)
            if len(payload) > MAX_BODY:
                raise ValueError("Snapshot too large")
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise ValueError("Snapshot must be an object")
            return data
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        raise UpstreamError("Snapshot service unavailable") from exc


class DecisionServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128

    def __init__(self, address: tuple[str, int], *, token: str, store: RunStore,
                 planning_url: str, participation_url: str, semantic_provider=None, workers=2, fact_collector=None,
                 jobs=None, worker_health=False):
        self.token, self.store = token, store
        self.planning_url, self.participation_url = planning_url, participation_url
        self.slots = threading.BoundedSemaphore(32)
        self.jobs = jobs or JobWorkers(store, semantic_provider, workers=workers, fact_collector=fact_collector)
        self.worker_health = worker_health
        super().__init__(address, DecisionHandler)
        if isinstance(self.jobs, JobWorkers):
            self.jobs.start()

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            self.shutdown_request(request)
            return
        request.settimeout(15)
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def server_close(self):
        super().server_close()
        self.jobs.close()


class DecisionHandler(BaseHTTPRequestHandler):
    server: DecisionServer

    def log_message(self, *args):
        pass

    def send_json(self, status, payload):
        if status >= 400:
            payload = {"code": payload.get("code", "INTERNAL"),
                       "message": payload.get("message", payload.get("code", "Request failed")),
                       "retryable": status >= 500 or status == 429,
                       "requestId": self.request_id}
        encoded = json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("x-request-id", self.request_id)
        if status == 202:
            self.send_header("Retry-After", "1")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        incoming = self.headers.get("x-request-id", "")
        self.request_id = incoming if SAFE_ID.fullmatch(incoming) else str(uuid4())
        started = time.monotonic()
        try:
            if self.path == "/health" and self.command == "GET":
                return self.send_json(200, {"status": "ok"})
            if self.path == "/health/ready" and self.command == "GET":
                try:
                    self.server.store.ping()
                    ready = (self.server.jobs.ready() if self.server.worker_health else self.server.store.supports(
                        [spec for kind, spec in self.server.jobs.specifications.items() if kind not in {'fact_collection', 'research'}]))
                except Exception:
                    return self.send_json(503, {'code': 'DATABASE_UNAVAILABLE'})
                if not ready:
                    return self.send_json(503, {'code': 'WORKERS_UNAVAILABLE'})
                return self.send_json(200, {"status": "ok"})
            if not hmac.compare_digest(self.headers.get("x-internal-token", ""), self.server.token):
                return self.send_json(401, {"code": "UNAUTHENTICATED"})
            body = {}
            if self.command == "POST":
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > MAX_BODY:
                    return self.send_json(413, {"code": "INVALID_INPUT"})
                body = json.loads(self.rfile.read(length) or b'{}')
                if not isinstance(body, dict):
                    raise SnapshotError("Body must be an object")
            self.dispatch(body)
        except (SnapshotError, InputError, ValueError, TypeError) as exc:
            self.send_json(400, {"code": "INVALID_INPUT", "message": str(exc)})
        except UpstreamError:
            self.send_json(503, {"code": "UPSTREAM_UNAVAILABLE"})
        except QueueFull:
            self.send_json(503, {"code": "JOB_CAPACITY_REACHED"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            logging.error("internal_failure request_id=%s type=%s", self.request_id, type(error).__name__)
            self.send_json(500, {"code": "INTERNAL"})
        finally:
            # No URL IDs, credentials, answers, or response bodies.
            logging.info("request_finished request_id=%s method=%s elapsed_ms=%d",
                         self.request_id, self.command, (time.monotonic()-started)*1000)

    def dispatch(self, body: dict) -> None:
        parts = self.path.strip('/').split('/')
        if self.path == "/internal/metrics" and self.command == "GET":
            return self.send_json(200, self.server.store.metrics())
        if self.server.worker_health:
            return self.send_json(404, {'code': 'NOT_FOUND'})
        if self.path == "/internal/planning/validate" and self.command == "POST":
            validate_planning_snapshot(body)
            return self.send_json(200, inspect_definition(body))
        if self.path == "/internal/previews" and self.command == "POST":
            plan, response = body.get("planning"), body.get("responses")
            if not isinstance(plan, dict) or not isinstance(response, dict) or len(response.get("participants", [])) != 1:
                raise SnapshotError("Preview needs one member and a published form")
            from .snapshots import map_snapshots
            mapped = deepcopy(plan)
            mapped["roster"] = [p["participant_id"] for p in response["participants"]]
            map_snapshots(mapped, response)
            run = self.server.jobs.enqueue(mapped, response, kind="preview", retry=body.get("retry") is True)
            return self.send_run(run)
        if self.path == "/internal/facts/collections" and self.command == "POST":
            if ('fact_collection' not in self.server.jobs.specifications or not self.server.store.supports(
                    [self.server.jobs.specifications['fact_collection']])):
                return self.send_json(503,{"code":"FACT_COLLECTOR_NOT_CONFIGURED"})
            from .fact_collection import public_collection_input
            planning = body.get("planning")
            safe = public_collection_input(planning,body.get("requests"))
            frozen = {key: planning[key] for key in ("plan_id","round_id","option_revision","option_snapshot_id")}
            frozen["collection_input"] = safe
            run = self.server.jobs.enqueue(frozen,{"snapshot_id":"fact-collection"},kind="fact_collection",retry=body.get("retry") is True)
            return self.send_run(run)
        if self.path == "/internal/research" and self.command == "POST":
            if 'research' not in self.server.jobs.specifications or not self.server.store.supports([self.server.jobs.specifications['research']]):
                return self.send_json(503, {"code": "FACT_COLLECTOR_NOT_CONFIGURED"})
            task = body.get("task")
            refs = body.get("refs") if isinstance(body.get("refs"), dict) else {}
            if task not in {"overviews", "questions", "facts"} or not isinstance(body.get("input"), dict) or not all(
                    isinstance(refs.get(key), str) and refs[key] for key in ("plan_id", "round_id")):
                return self.send_json(400, {"code": "INVALID_INPUT"})
            # Only the organiser's option names, links, plan question and region reach providers.
            frozen = {"plan_id": refs["plan_id"], "round_id": refs["round_id"], "option_revision": 0,
                      "option_snapshot_id": "research", "research_task": task, "research_input": body["input"]}
            run = self.server.jobs.enqueue(frozen, {"snapshot_id": "research"}, kind="research", retry=body.get("retry") is True)
            return self.send_run(run)
        if len(parts) == 3 and parts[:2] == ["internal", "places"] and self.command == "GET":
            from .research import Researcher
            from .places import PlacesClient
            from .fact_collection import CollectionUnavailable
            try:
                card = Researcher(None, PlacesClient() if os.environ.get("GOOGLE_PLACES_API_KEY") else None).place_card(parts[2])
            except CollectionUnavailable as error:
                return self.send_json(503 if error.code != "PLACES_HTTP_404" else 404, {"code": error.code})
            return self.send_json(200, card)
        if len(parts) >= 5 and parts[:2] == ["internal", "places"] and parts[3] == "photos" and self.command == "GET":
            from .research import Researcher
            from .places import PlacesClient
            from .fact_collection import CollectionUnavailable
            name = "/".join(["places", parts[2], "photos", parts[4].split("?")[0]])
            try:
                payload, kind = Researcher(None, PlacesClient() if os.environ.get("GOOGLE_PLACES_API_KEY") else None).photo(name, 800)
            except CollectionUnavailable as error:
                return self.send_json(503, {"code": error.code})
            if not kind.startswith("image/"):
                return self.send_json(502, {"code": "PLACES_UNAVAILABLE"})
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "private, max-age=3600")
            self.end_headers()
            self.wfile.write(payload)
            return
        if len(parts) == 4 and parts[:2] == ["internal", "rounds"] and parts[3] == "recommendations" and self.command == "POST":
            return self.recommend(str(UUID(parts[2])),retry=body.get("retry") is True)
        if len(parts) in {3, 4, 5} and parts[:2] == ["internal", "runs"]:
            run = self.server.store.get(str(UUID(parts[2])))
            if not run:
                return self.send_json(404, {"code": "NOT_FOUND"})
            if len(parts) == 3 and self.command == "GET":
                return self.send_run(run)
            if len(parts) == 5 and parts[3] == "clarifications" and self.command == "GET":
                if run["status"] == "pending":
                    return self.send_json(202, public_result(run))
                member_id = str(UUID(parts[4]))
                if member_id not in run.get("member_states", {}):
                    return self.send_json(403, {"code": "FORBIDDEN"})
                return self.send_json(200, member_review(run, member_id))
            if len(parts) == 4 and parts[3] == "validate-selection" and self.command == "POST":
                return self.validate_selection(run, body)
        self.send_json(404, {"code": "NOT_FOUND"})

    def send_run(self, run):
        logging.info("run_response request_id=%s run_id=%s job_state=%s",self.request_id,run["run_id"],run.get("job_state","completed"))
        return self.send_json(202 if run["status"] == "pending" else 200, public_result(run))

    def recommend(self, round_id: str, *, retry=False) -> None:
        planning = read_snapshot(self.server.planning_url, f"/internal/rounds/{round_id}/option-snapshot", self.server.token, self.request_id)
        responses = read_snapshot(self.server.participation_url, f"/internal/rounds/{round_id}/response-snapshot", self.server.token, self.request_id)
        from .snapshots import map_snapshots
        map_snapshots(planning, responses)
        return self.send_run(self.server.jobs.enqueue(planning, responses,retry=retry))

    def validate_selection(self, run: dict, body: dict) -> None:
        if body.get("input_refs") != run["input_refs"] or run["status"] != "ranked":
            return self.send_json(409, {"code": "STALE_OR_BLOCKED_RESULT"})
        rows = run["result"].get("ranked_candidates", [])
        key = "option_id" if run["algorithm_input"]["context"]["schema_version"] == "generic-option-v1" else "candidate_id"
        if not any(row[key] == body.get("candidate_id") for row in rows):
            return self.send_json(409, {"code": "INELIGIBLE_CANDIDATE"})
        candidate = next(row for row in run["algorithm_input"]["candidates"] if row[key] == body["candidate_id"])
        details = {"candidate": deepcopy(candidate), "context": {
            name: run["algorithm_input"]["context"][name]
            for name in ("schema_version", "algorithm_version", "currency", "cost_scope", "timezone")
            if name in run["algorithm_input"]["context"]}}
        return self.send_json(200, {"run_id": run["run_id"], "candidate_id": body["candidate_id"],
                                    "input_refs": run["input_refs"], "selected_details": details})
