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
import os, re, ssl, json, sys, traceback, importlib, uuid, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from asset_handler        import handle_upload, handle_get_files
from async_agent_handler  import handle_async_agent
from flow_resume          import save_run

SSL_PORT = int(os.getenv("SSL_PORT", "8000"))
SSL_CERT = os.getenv("SSL_CERT_PATH")
SSL_KEY  = os.getenv("SSL_KEY_PATH")


class FlowManagerRequestHandler(BaseHTTPRequestHandler):

    # ───────────────────────── GET ──────────────────────────
    def do_GET(self):
        if self.path.startswith("/files"):
            return handle_get_files(self)
        self.send_response(404); self.end_headers()

    # ───────────────────────── POST ─────────────────────────
    def do_POST(self):

        # 1) /upload  (assets)
        if self.path == "/upload":
            return handle_upload(self)

        # 2) /async_agent  (human/async callback)
        if self.path == "/async_agent":
            return handle_async_agent(self)

        # 3) /  flow invocation -------------
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            return self._error(400, {"error": "Invalid JSON"})

        flow = req.get("flow")
        if not flow or not re.fullmatch(r"[A-Za-z0-9_]+", flow):
            return self._error(400, {"error": "Missing or invalid flow name"})

        # Hot-reload?
        if req.get("flow_reload"):
            sys.modules.pop(f"flows.{flow}", None)

        # import flow module
        try:
            mod = importlib.import_module(f"flows.{flow}")
        except ImportError as e:
            return self._error(404, {"error": f"No such flow '{flow}': {e}"})

        try:
            if req.get("stream"):
                self._handle_streaming(mod, req, flow)
            else:
                self._handle_non_stream(mod, req, flow)
        except Exception:
            traceback.print_exc()
            self._error(500, {"error": "Internal server error"})

    # ──────────────────── streaming -------------------------
    def _handle_streaming(self, mod, req, flow_name):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        run_id = str(uuid.uuid4())

        for update in mod.run(
            context=req.get("context", {}),
            query=req.get("query", {}),
            file_id=req.get("file_id"),
            stream=True,
        ):
            # Pause requested?
            if update.get("pause"):
                save_run(
                    run_id      = run_id,
                    flow_name   = flow_name,
                    state       = update["state"],
                    next_node   = update["next_node"]
                )
                payload = {"info": "paused", "run_id": run_id}
                self._send_chunk(json.dumps(payload).encode() + b"\n")
                self._send_chunk(b"", end=True)
                return

            # normal update
            self._send_chunk(json.dumps(update).encode() + b"\n")

        self._send_chunk(b"", end=True)

    # ─────────────────── non-stream -------------------------
    def _handle_non_stream(self, mod, req, flow_name):
        run_id = str(uuid.uuid4())
        gen = mod.run(
            context=req.get("context", {}),
            query=req.get("query", {}),
            file_id=req.get("file_id"),
            stream=False,
        )
        first = next(gen, {})

        # If paused return a small object
        if first.get("pause"):
            save_run(
                run_id    = run_id,
                flow_name = flow_name,
                state     = first["state"],
                next_node = first["next_node"]
            )
            body = json.dumps({"info":"paused","run_id":run_id}).encode()
        else:
            body = json.dumps(first).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ─────────────────── helpers ----------------------------
    def _send_chunk(self, data: bytes, end: bool=False):
        if end:
            self.wfile.write(b"0\r\n\r\n")
        else:
            self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()

    def _error(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ───────────────────────── server --------------------------
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

