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
import os, re, ssl, json, sys, traceback, importlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from asset_handler  import handle_upload, handle_get_files
from async_agent_handler import handle_async_agent   # NEW ⬅

SSL_PORT = int(os.getenv("SSL_PORT", "8000"))
SSL_CERT = os.getenv("SSL_CERT_PATH")
SSL_KEY  = os.getenv("SSL_KEY_PATH")


class FlowManagerRequestHandler(BaseHTTPRequestHandler):

    # ─────────────────────────── GET ────────────────────────────
    def do_GET(self):
        if self.path.startswith("/files"):
            return handle_get_files(self)             # asset manager
        self.send_response(404)
        self.end_headers()

    # ─────────────────────────── POST ───────────────────────────
    def do_POST(self):
        # 1) binary upload  → asset_handler
        if self.path == "/upload":
            return handle_upload(self)

        # 2) async-agent callback  → async_agent_handler   NEW ⬅
        if self.path == "/async_agent":
            return handle_async_agent(self)

        # 3) otherwise treat as flow invocation
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            return self._error(400, {"error": "Invalid JSON"})

        flow = req.get("flow")
        if not flow or not re.fullmatch(r"[A-Za-z0-9_]+", flow):
            return self._error(400, {"error": "Missing or invalid flow name"})

        # Hot-reload flow code if requested
        if req.get("flow_reload"):
            mod_name = f"flows.{flow}"
            if mod_name in sys.modules:
                del sys.modules[mod_name]

        try:
            mod = importlib.import_module(f"flows.{flow}")
        except ImportError as e:
            print(f"Could not import {flow}: {e}", flush=True)
            return self._error(404, {"error": f"No such flow '{flow}': {e}"})

        try:
            if req.get("stream"):
                self._handle_streaming(mod, req)
            else:
                self._handle_non_stream(mod, req)
        except Exception:
            traceback.print_exc()
            self._error(500, {"error": "Internal server error"})

    # ─────────────────────── Streaming helper ───────────────────
    def _handle_streaming(self, mod, req):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        for update in mod.run(
            context=req.get("context", {}),
            query=req.get("query", {}),
            file_id=req.get("file_id", None),
            stream=True,
        ):
            chunk = (json.dumps(update) + "\n").encode("utf-8")
            self._send_chunk(chunk)

        self._send_chunk(b"", end=True)   # terminator

    # ───────────────────── Non-stream helper ────────────────────
    def _handle_non_stream(self, mod, req):
        gen   = mod.run(
            context=req.get("context", {}),
            query=req.get("query", {}),
            file_id=req.get("file_id", None),
            stream=False,
        )
        first = next(gen, {})
        body  = json.dumps(first).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ──────────────────────── Chunk helper ──────────────────────
    def _send_chunk(self, data: bytes, end: bool = False):
        if end:
            self.wfile.write(b"0\r\n\r\n")
        else:
            size = f"{len(data):X}\r\n".encode("utf-8")
            self.wfile.write(size + data + b"\r\n")
        self.wfile.flush()

    # ─────────────────────── Error helper ───────────────────────
    def _error(self, code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ────────────────────────────── Server ─────────────────────────
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

