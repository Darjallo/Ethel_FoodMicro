# Project Ethel
# Flow Manager API
#
# Copyright (C) 2025  Gerd Kortemeyer, ETH Zurich
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# flow_manager.py
#
import os, re, ssl, json, sys, traceback, importlib, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from flow_resume import runs
from async_agent_handler import handle_async_agent

SSL_PORT = int(os.getenv("SSL_PORT", "8000"))
SSL_CERT = os.getenv("SSL_CERT_PATH")
SSL_KEY  = os.getenv("SSL_KEY_PATH")


class FlowManagerRequestHandler(BaseHTTPRequestHandler):
    # ───────────────────────────────────────────────── GET ──────────────────────────────────────────────
    def do_GET(self):
        # ── /run/<id> : resume metadata ────────────────────────────────────────────────────────────────
        if self.path.startswith("/run/"):
            run_id = self.path.split("/run/")[1]
            doc = runs.find_one({"_id": run_id}, projection={"state": False})
            if doc:
                body = json.dumps(doc, default=str).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._error(404, {"error": "run not found"})
            return

        # any other GET → 404
        self.send_response(404)
        self.end_headers()

    # ───────────────────────────────────────────────── POST ─────────────────────────────────────────────
    def do_POST(self):
        # async agent passthrough (kept)
        if self.path == "/async_agent":
            return handle_async_agent(self)

        # ── normal flow invocation ────────────────────────────────────────────────────────────────────
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            return self._error(400, {"error": "Invalid JSON"})

        # tenant is mandatory
        tenant = req.get("tenant")
        if not tenant or not isinstance(tenant, str):
            return self._error(400, {"error": "Missing or invalid tenant"})
        context = req.get("context", {}) or {}
        context["tenant"] = tenant

        flow = req.get("flow")
        if not flow or not re.fullmatch(r"[A-Za-z0-9_]+", flow):
            return self._error(400, {"error": "Missing or invalid flow name"})

        if req.get("flow_reload"):
            sys.modules.pop(f"flows.{flow}", None)

        try:
            mod = importlib.import_module(f"flows.{flow}")
        except ImportError as e:
            return self._error(404, {"error": f"No such flow '{flow}': {e}"})

        try:
            if req.get("stream"):
                self._handle_streaming(
                    mod,
                    context,
                    req.get("query", {}),
                    req.get("file_id"),
                    flow,
                )
            else:
                self._handle_non_stream(
                    mod,
                    context,
                    req.get("query", {}),
                    req.get("file_id"),
                    flow,
                )
        except Exception:
            traceback.print_exc()
            self._error(500, {"error": "Internal server error"})

    # ───────────────────────────────────────────── helpers ─────────────────────────────────────────────
    def _handle_streaming(self, mod, context, query, file_id, flow_name):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        run_id = str(uuid.uuid4())
        for update in mod.run(context=context, query=query, file_id=file_id, stream=True):
            if update.get("pause"):
                from flow_resume import save_run
                save_run(run_id, flow_name, update["state"], update["next_node"])
                pause_payload = {k: v for k, v in update.items() if k != "state"}
                pause_payload.update({"info": "paused", "run_id": run_id})
                self._send_chunk(json.dumps(pause_payload).encode() + b"\n")
                self._send_chunk(b"", end=True)
                return

            self._send_chunk(json.dumps(update).encode() + b"\n")

        self._send_chunk(b"", end=True)

    def _handle_non_stream(self, mod, context, query, file_id, flow_name):
        gen   = mod.run(context=context, query=query, file_id=file_id, stream=False)
        first = next(gen, {})

        if first.get("pause"):
            from flow_resume import save_run
            run_id = str(uuid.uuid4())
            save_run(run_id, flow_name, first["state"], first["next_node"])
            body_dict = {k: v for k, v in first.items() if k != "state"}
            body_dict.update({"info": "paused", "run_id": run_id})
        else:
            body_dict = first

        body = json.dumps(body_dict).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # chunked helper
    def _send_chunk(self, data: bytes, end: bool = False):
        if end:
            self.wfile.write(b"0\r\n\r\n")
        else:
            self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()

    # error helper
    def _error(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ───────────────────────────────────────────── server bootstrap ────────────────────────────────────────
def run_server():
    server = ThreadingHTTPServer(("0.0.0.0", SSL_PORT), FlowManagerRequestHandler)
    if SSL_CERT and SSL_KEY:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(SSL_CERT, SSL_KEY)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    print(f"Flow manager listening on port {SSL_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()

