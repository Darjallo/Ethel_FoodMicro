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
import importlib, json, re, ssl, os, traceback, requests
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ssl_port = int(os.getenv("SSL_PORT", "8000"))
ssl_cert = os.getenv("SSL_CERT_PATH")
ssl_key  = os.getenv("SSL_KEY_PATH")

class FlowManagerRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            req = json.loads(raw)
        except:
            return self._error(400, {"error":"Invalid JSON"})

        flow = req.get("flow")
        if not flow or not re.match(r"^[A-Za-z0-9_]+$", flow):
            return self._error(400, {"error":"Bad flow"})
        try:
            mod = importlib.import_module(f"flows.{flow}")
        except ImportError:
            return self._error(404, {"error":f"No such flow '{flow}'"})

        try:
            if req.get("stream"):
                self._streaming(mod, req)
            else:
                self._nonstream(mod, req)
        except Exception:
            traceback.print_exc()
            self._error(500, {"error":"Internal error"})

    def _streaming(self, mod, req):
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Transfer-Encoding","chunked")
        self.end_headers()

        for update in mod.run(
            req.get("context"), req.get("session"),
            req.get("query",{}), stream=True
        ):
            chunk = (json.dumps(update) + "\n").encode("utf-8")
            self.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
            self.wfile.flush()

        # terminator
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _nonstream(self, mod, req):
        gen = mod.run(
            req.get("context"), req.get("session"),
            req.get("query",{}), stream=False
        )
        first = next(gen, {})
        body = json.dumps(first).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

def run_server():
    server = ThreadingHTTPServer(("0.0.0.0", ssl_port), FlowManagerRequestHandler)
    if ssl_cert and ssl_key:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(ssl_cert, ssl_key)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    print(f"listening on port {ssl_port}")
    server.serve_forever()

if __name__=="__main__":
    run_server()

