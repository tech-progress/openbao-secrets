import hmac
import http.client
import json
import os
import resource
import signal
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


MAX_BODY = 16 * 1024 * 1024
GATE_HEADER = "X-Template-Operator-Key"
HOP_HEADERS = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "proxy-authenticate", "proxy-authorization"}


def canonical_path(target):
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.fragment or not parsed.path.startswith("/"):
        raise ValueError("Invalid request target")
    if "%" in parsed.path or "\\" in parsed.path or "//" in parsed.path:
        raise ValueError("Encoded or ambiguous paths are not supported")
    if any(part in {".", ".."} for part in parsed.path.split("/")):
        raise ValueError("Dot segments are not supported")
    return parsed.path


def data_plane_path(path):
    return path.startswith(("/v1/secret/", "/v1/transit/")) or path == "/v1/auth/approle/login"


def upstream_request(method, target, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", 8200, timeout=15)
    try:
        connection.request(method, target, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read(MAX_BODY + 1)
        if len(payload) > MAX_BODY:
            raise ValueError("Upstream response exceeds gateway limit")
        return response.status, response.getheaders(), payload
    finally:
        connection.close()


class Gateway(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def send_payload(self, status, payload, headers=None):
        self.send_response(status)
        for key, value in headers or []:
            if key.lower() not in HOP_HEADERS | {"content-length", "server", "date", "location"}:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)
        self.close_connection = True

    def error(self, status, message):
        self.send_payload(status, json.dumps({"errors": [message]}).encode(), [("Content-Type", "application/json")])

    def stream_snapshot(self, length):
        connection = http.client.HTTPConnection("127.0.0.1", 8200, timeout=60)
        try:
            connection.putrequest(self.command, self.path)
            connection.putheader("Content-Length", str(length))
            for key in ("X-Vault-Token", "X-Bao-Token", "Content-Type"):
                if self.headers.get(key):
                    connection.putheader(key, self.headers[key])
            connection.endheaders()
            remaining = length
            while remaining:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    raise ValueError("Incomplete snapshot")
                connection.send(chunk)
                remaining -= len(chunk)
            response = connection.getresponse()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in HOP_HEADERS | {"server", "date", "location"}:
                    self.send_header(key, value)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                while chunk := response.read(65536):
                    self.wfile.write(chunk)
            self.close_connection = True
        finally:
            connection.close()

    def handle_api(self):
        try:
            path = canonical_path(self.path)
        except ValueError:
            self.error(400, "Invalid or ambiguous request path")
            return
        if path in {"/healthz", "/readyz"} and self.command in {"GET", "HEAD"}:
            try:
                _, _, payload = upstream_request("GET", "/v1/sys/health")
                state = json.loads(payload)
                initialized, sealed = state["initialized"], state["sealed"]
                status = 200 if path == "/healthz" or initialized and not sealed else 503
                self.send_payload(status, json.dumps({"process_alive": True, "initialized": initialized, "sealed": sealed}).encode(), [("Content-Type", "application/json")])
            except (OSError, ValueError, KeyError, http.client.HTTPException):
                self.error(503, "Backend unavailable")
            return
        supplied = self.headers.get_all(GATE_HEADER, [])
        operator = len(supplied) == 1 and hmac.compare_digest(supplied[0].encode(), self.server.gate_key.encode())
        if not path.startswith("/v1/"):
            self.error(404, "UI disabled; use the API")
            return
        if not operator and not (self.server.public_data_plane and data_plane_path(path)):
            self.error(403, "Operator gate required")
            return
        if self.headers.get("Transfer-Encoding"):
            self.error(400, "Chunked requests are not supported")
            return
        lengths = self.headers.get_all("Content-Length", [])
        snapshot = operator and path in {"/v1/sys/storage/raft/snapshot", "/v1/sys/storage/raft/snapshot-force"} and self.command in {"GET", "POST"}
        try:
            if len(lengths) > 1:
                raise ValueError()
            length = int(lengths[0]) if lengths else 0
            if not 0 <= length <= (5 * 1024 ** 3 if snapshot else MAX_BODY):
                raise ValueError()
        except ValueError:
            self.error(413, "Invalid content length or body exceeds gateway limit")
            return
        if snapshot:
            try:
                self.stream_snapshot(length)
            except (OSError, ValueError, http.client.HTTPException):
                self.close_connection = True
            return
        body = self.rfile.read(length) if length else None
        if body is not None and len(body) != length:
            self.error(400, "Incomplete request body")
            return
        blocked = HOP_HEADERS | {"host", "content-length", GATE_HEADER.lower(), "forwarded", "x-forwarded-for", "x-forwarded-proto", "x-forwarded-host"}
        headers = {key: value for key, value in self.headers.items() if key.lower() not in blocked}
        try:
            status, response_headers, payload = upstream_request(self.command, self.path, body, headers)
            self.send_payload(status, payload, response_headers)
        except (OSError, ValueError, http.client.HTTPException):
            self.error(502, "Backend request failed")

    do_GET = do_POST = do_PUT = do_DELETE = do_LIST = do_HEAD = handle_api


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        self.capacity = threading.BoundedSemaphore(32)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.capacity.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.capacity.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.capacity.release()


def main():
    gate_key = os.environ.get("OPERATOR_GATE_KEY", "")
    if len(gate_key) < 32 or not gate_key.isascii() or any(character.isspace() for character in gate_key):
        raise SystemExit("OPERATOR_GATE_KEY must be a random ASCII key of at least 32 characters")
    public_data_plane = os.environ.get("PUBLIC_DATA_PLANE", "false")
    if public_data_plane not in {"true", "false"}:
        raise SystemExit("PUBLIC_DATA_PLANE must be true or false")
    api_address = os.environ.get("BAO_API_ADDR", "")
    parsed = urlsplit(api_address)
    if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise SystemExit("BAO_API_ADDR must be an origin without credentials or path")
    local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
    if parsed.scheme != "https" and not local_http:
        raise SystemExit("BAO_API_ADDR requires HTTPS except for loopback tests")
    port = int(os.environ.get("PORT", "8080"))
    if not 1024 <= port <= 65535 or port in {8200, 8201}:
        raise SystemExit("PORT must be unprivileged and not a backend port")
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.makedirs("/data", exist_ok=True)
    if os.geteuid() == 0:
        os.chown("/data", 10001, 10001)
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
    os.makedirs("/data/raft", exist_ok=True)
    config = f'''ui = false
api_addr = {json.dumps(api_address)}
cluster_addr = "https://127.0.0.1:8201"
log_level = "warn"
storage "raft" {{
  path = "/data/raft"
  node_id = "railway-openbao"
}}
listener "tcp" {{
  address = "127.0.0.1:8200"
  cluster_address = "127.0.0.1:8201"
  tls_disable = true
}}
audit "file" "persistent" {{
  description = "Persistent single-node audit"
  options {{
    file_path = "/data/audit.log"
  }}
}}
'''
    config_path = "/tmp/openbao-config.hcl"
    with open(config_path, "w", encoding="utf-8") as config_file:
        config_file.write(config)
    child_environment = {key: value for key, value in os.environ.items() if key not in {"OPERATOR_GATE_KEY", "PUBLIC_DATA_PLANE"}}
    backend = subprocess.Popen(["/usr/bin/bao", "server", "-config=" + config_path], env=child_environment)
    gateway = BoundedServer(("0.0.0.0", port), Gateway)
    gateway.gate_key = gate_key
    gateway.public_data_plane = public_data_plane == "true"
    worker = threading.Thread(target=gateway.serve_forever, daemon=True)
    worker.start()

    def stop(signum, frame):
        backend.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    exit_code = backend.wait()
    gateway.shutdown()
    gateway.server_close()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
