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
import importlib
import json
import re
import ssl
import os
import traceback

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ssl_port = int(os.getenv("SSL_PORT", "8000"))
ssl_cert = os.getenv("SSL_CERT_PATH")
ssl_key  = os.getenv("SSL_KEY_PATH")

class FlowManagerRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # 1) parse & validate JSON
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            return self._reply(400, {"error": "Invalid JSON"})

        flow   = req.get("flow")
        stream = req.get("stream", False)
        if not flow or not re.fullmatch(r"[A-Za-z0-9_]+", flow):
            return self._reply(400, {"error": "Missing or invalid flow name"})

        # 2) import the flow module
        try:
            mod = importlib.import_module(f"flows.{flow}")
        except ImportError:
            return self._reply(404, {"error": f"No such flow '{flow}'"})

        # 3) run in streaming or non-streaming mode
        try:
            if stream:
                self._handle_streaming(mod, req)
            else:
                self._handle_nonstream(mod, req)
        except Exception:
            traceback.print_exc()
            self._reply(500, {"error": "Internal server error"})

    def _handle_streaming(self, mod, req):
        # begin chunked JSON
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        for update in mod.run(
            req.get("context"),
            req.get("session"),
            req.get("query", {}),
            stream=True
        ):
            chunk = (json.dumps(update) + "\n").encode("utf-8")
            self._send_chunk(chunk)

        # final zero-length chunk
        self._send_chunk(b"", end=True)

    def _handle_nonstream(self, mod, req):
        # consume all yields, take the last one
        last = None
        for update in mod.run(
            req.get("context"),
            req.get("session"),
            req.get("query", {}),
            stream=False
        ):
            last = update

        if last is None:
            # nothing yielded → No Content
            self.send_response(204)
            self.end_headers()
            return

        data = json.dumps(last).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _reply(self, status: int, payload: dict):
        b = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _send_chunk(self, data: bytes, end: bool = False):
        if end:
            # terminator for chunked encoding
            self.wfile.write(b"0\r\n\r\n")
        else:
            size = f"{len(data):X}\r\n".encode("utf-8")
            self.wfile.write(size + data + b"\r\n")
        self.wfile.flush()

def run_server(port=8000, certfile=None, keyfile=None):
    server = ThreadingHTTPServer(("0.0.0.0", port), FlowManagerRequestHandler)
    if certfile and keyfile:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile, keyfile)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    print(f"Flow manager listening on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    run_server(port=ssl_port, certfile=ssl_cert, keyfile=ssl_key)

