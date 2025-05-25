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
import importlib, json, re, ssl, os, traceback
import requests
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ssl_port = int(os.getenv("SSL_PORT", "8000"))
ssl_cert = os.getenv("SSL_CERT_PATH")
ssl_key = os.getenv("SSL_KEY_PATH")

class FlowManagerRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        req_json = json.loads(self.rfile.read(content_length))

        flow_name = req_json.get("flow")
        context = req_json.get("context")
        session = req_json.get("session")
        query = req_json.get("query", {})
        stream = req_json.get("stream", False)

        flow_module = importlib.import_module(f"flows.{flow_name}")

        if stream:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Transfer-Encoding', 'chunked')
            self.end_headers()

            livestream_active = False
            for chunk in flow_module.run(context, session, query, stream=True):
                if 'livestream' in chunk:
                    # Begin livestream side-channel
                    livestream_node = chunk['livestream']
                    livestream_active = True
                    self._livestream_from_node(livestream_node, context, session, query)
                    livestream_active = False
                else:
                    # Regular LangGraph streaming
                    if not livestream_active:
                        chunk_bytes = (json.dumps(chunk) + "\n").encode("utf-8")
                        self._send_chunk(chunk_bytes)
            self._send_chunk(b'', end=True)  # end of stream
        else:
            result = next(flow_module.run(context, session, query, stream=False))
            resp = json.dumps(result).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

    def _livestream_from_node(self, node_name, context, session, query):
        url = f"http://{node_name}:8000/"
        payload = {
            "context": context,
            "session": session,
            "query": query,
            "stream": True
        }
        with requests.post(url, json=payload, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=1):
                if chunk:
                    self._send_chunk(chunk)

    def _send_chunk(self, chunk, end=False):
        if end:
            self.wfile.write(b"0\r\n\r\n")
        else:
            self.wfile.write(b"%X\r\n" % len(chunk))
            self.wfile.write(chunk + b"\r\n")
        self.wfile.flush()

def run_server(port=8000, certfile=None, keyfile=None):
    server = ThreadingHTTPServer(("0.0.0.0", port), FlowManagerRequestHandler)
    if certfile and keyfile:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile, keyfile)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    print(f"Flow manager listening on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    run_server(port=ssl_port, certfile=ssl_cert, keyfile=ssl_key)

