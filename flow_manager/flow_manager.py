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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import traceback

ssl_port = int(os.getenv("SSL_PORT", "8000"))
ssl_cert = os.getenv("SSL_CERT_PATH")
ssl_key = os.getenv("SSL_KEY_PATH")

class FlowManagerRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(content_length)
        try:
            req_json = json.loads(data)
        except Exception:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error": "Invalid JSON"}')
            return

        flow_name = req_json.get("flow")
        context = req_json.get("context")
        session = req_json.get("session")
        query = req_json.get("query", {})
        stream = req_json.get("stream", False)

        if not flow_name:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "Missing flow parameter"}')
            return

        if not re.match(r'^[A-Za-z0-9_]+$', flow_name):
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "Invalid flow name"}')
            return

        # Dynamically import the flow
        try:
            flow_module = importlib.import_module(f"flows.{flow_name}")
        except Exception as e:
            print(f"ImportError: {e}", flush=True)
            traceback.print_exc()
            self.send_response(404)
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"No such flow '{flow_name}'"}).encode())
            return

        try:
            if stream:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()
                for chunk in flow_module.run(context, session, query, stream=True):
                    if isinstance(chunk, dict):
                        chunk = json.dumps(chunk)
                    chunk = f"data: {chunk}\n\n"
                    chunk_bytes = chunk.encode("utf-8")
                    self.wfile.write(b"%X\r\n" % len(chunk_bytes))
                    self.wfile.write(chunk_bytes)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                # End of stream, as OpenAI does
                done_bytes = b"data: [DONE]\n\n"
                self.wfile.write(b"%X\r\n" % len(done_bytes))
                self.wfile.write(done_bytes)
                self.wfile.write(b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            else:
                result = flow_module.run(context, session, query, stream=False)
                # Always expect a generator, per your new policy
                # Exhaust it and get first item (or list, if you prefer)
                if hasattr(result, "__iter__") and not isinstance(result, dict) and not isinstance(result, list):
                    # Exhaust generator
                    result_items = list(result)
                    if len(result_items) == 1:
                        result = result_items[0]
                    elif len(result_items) == 0:
                        self.send_response(204)  # No content
                        self.end_headers()
                        return
                    else:
                        # More than one item? You decide: here, return the list
                        result = result_items
                resp = json.dumps(result).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
        except Exception as e:
            print("==== INTERNAL SERVER ERROR ====", flush=True)
            print(str(e), flush=True)
            traceback.print_exc()
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

def run_server(port=8000, certfile=None, keyfile=None):
    server = ThreadingHTTPServer(("0.0.0.0", port), FlowManagerRequestHandler)
    if certfile and keyfile:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile, keyfile)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        protocol = "https"
    else:
        protocol = "http"
    print(f"Flow manager listening on {protocol}://0.0.0.0:{port}")
    server.serve_forever()

if __name__ == "__main__":
    run_server(port=ssl_port, certfile=ssl_cert, keyfile=ssl_key)

