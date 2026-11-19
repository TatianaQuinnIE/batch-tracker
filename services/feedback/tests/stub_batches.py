"""A stand-in for the batches service, for the feedback tests (ADR-9).

A real HTTP server on 127.0.0.1 with a random port, so the feedback code under
test goes through urllib, sockets and timeouts exactly as it does in production.
Its responses use the shapes in services/batches/openapi.yaml; test_contract.py
checks that they still match that document.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BATCHES = [
    {"batch_code": "LAV-2607", "product": "Lavender soap bar", "produced_on": "2026-07-01",
     "expires_on": "2027-07-01", "quantity": 120, "status": "ok"},
    {"batch_code": "ROS-2608", "product": "Rosehip face oil", "produced_on": "2026-08-15",
     "expires_on": "2026-11-05", "quantity": 45, "status": "expired"},
]


class StubBatches:
    """mode: "ok", "slow" (answers after the timeout), "error" (500) or "html" (not JSON)."""

    def __init__(self):
        self.mode = "ok"
        self.delay_s = 3
        self.requests = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                stub.requests.append(self.path)
                if stub.mode == "slow":
                    time.sleep(stub.delay_s)
                if stub.mode == "error":
                    return self._send(500, {"error": "internal error"})
                if stub.mode == "html":
                    return self._send(502, None, b"<html>Bad gateway</html>", "text/html")
                if self.path == "/batches":
                    return self._send(200, BATCHES)
                code = self.path.removeprefix("/batches/")
                match = next((b for b in BATCHES if b["batch_code"] == code), None)
                if match is None:
                    return self._send(404, {"error": f"batch {code} not found"})
                return self._send(200, match)

            def _send(self, status, body, raw=None, content_type="application/json"):
                payload = raw if raw is not None else json.dumps(body).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the client gave up (timeout test); nothing to answer

            def log_message(self, *args):
                pass  # keep pytest output quiet

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
