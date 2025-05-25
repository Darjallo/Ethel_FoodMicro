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
import requests

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ssl_port = int(os.getenv("SSL_PORT", "8000"))
ssl_cert = os.getenv("SSL_CERT_PATH")
ssl_key = os.getenv("SSL_KEY_PATH")

class FlowManagerRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # 1) parse and validate
        length = int(self.headers.get('Content-Length', 0))
        raw    = self.rfile.read(length)
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(b'{"error":"Invalid JSON"}')
            return

        flow_name = req.get("flow")
        stream    = req.get("stream", False)
        if not flow_name or not re.match(r'^[A-Za-z0-9_]+$', flow_name):
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error":"Missing or invalid flow name"}')
            return

        # 2) import the flow
        try:
            flow_mod = importlib.import_module(f"flows.{flow_name}")
        except ImportError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(
                json.dumps({"error":f"No such flow '{flow_name}'"}).encode()
            )
            return

        # 3) dispatch to streaming or one-shot
        try:
            if stream:
                self._handle_streaming(flow_mod, req)
            else:
                self._handle_nonstream(flow_mod, req)
        except Exception:
            traceback.print_exc()
            self.send_response(500)
            self.end_headers()
            self.wfile.write(
                json.dumps({"error":"Internal server error"}).encode()
            )

    def _handle_streaming(self, flow_mod, req):
        # a) start chunked JSON
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Transfer-Encoding','chunked')
        self.end_headers()

        # b) for each update from your flow...
        for chunk in flow_mod.run(
            req.get("context"),
            req.get("session"),
            req.get("query", {}),
            stream=True
        ):
            # — if it contains a livestream instruction, open side-channel
            agent_to_stream = chunk.get("livestream")
            if agent_to_stream:
                self._stream_from_agent(agent_to_stream, req)
                continue

            # — otherwise, emit this update as JSON
            data = (json.dumps(chunk) + "\n").encode("utf-8")
            self._send_chunk(data)

        # c) terminate
        self._send_chunk(b"", end=True)

    def _stream_from_agent(self, agent_name, req):
        # clone the same call but with stream=True
        url = f"http://{agent_name}:8000/"
        payload = {
            "context": req.get("context"),
            "session": req.get("session"),
            "query":   req.get("query", {}),
            "stream":  True
        }
        with requests.post(url, json=payload, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            # forward raw bytes as small JSON chunks
            for block in resp.iter_content(chunk_size=1024):
                if not block:
                    continue
                text = block.decode("utf-8", errors="replace")
                wrap = {"livestream_data": text}
                data = (json.dumps(wrap) + "\n").encode("utf-8")
                self._send_chunk(data)

    def _handle_nonstream(self, flow_mod, req):
        # pull the first (and only) yield from run(...,stream=False)
        gen    = flow_mod.run(
            req.get("context"),
            req.get("session"),
            req.get("query", {}),
            stream=False
        )
        result = next(gen, {})
        body   = json.dumps(result).encode("utf-8")

        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_chunk(self, data: bytes, end: bool=False):
        if end:
            # zero-length chunk signals end
            self.wfile.write(b"0\r\n\r\n")
        else:
            size = f"{len(data):X}\r\n".encode()
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

if __name__=="__main__":
    run_server(port=ssl_port, certfile=ssl_cert, keyfile=ssl_key)

