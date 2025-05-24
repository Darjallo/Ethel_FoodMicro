# Project Ethel
# Base for all agents
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
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class AgentRequestHandler(BaseHTTPRequestHandler):
    # Set at runtime: AgentRequestHandler.business_logic = handler instance
    business_logic = None

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        raw_data = self.rfile.read(content_length)
        try:
            req_json = json.loads(raw_data.decode())
        except Exception:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error": "Invalid JSON"}')
            return

        stream = req_json.get("stream", False)
        if stream and hasattr(self.business_logic, "stream"):
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Transfer-Encoding', 'chunked')
            self.end_headers()
            # Write streamed chunks using HTTP chunked transfer
            for chunk in self.business_logic.stream(req_json):
                # Convert everything to string, just in case
                if not isinstance(chunk, str):
                    chunk = str(chunk)
                chunk_bytes = chunk.encode("utf-8")
                self.wfile.write(b"%X\r\n" % len(chunk_bytes))
                self.wfile.write(chunk_bytes)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        else:
            result = self.business_logic.handle(req_json)
            resp = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

def run_server(port, handler_instance):
    AgentRequestHandler.business_logic = handler_instance
    server = ThreadingHTTPServer(("0.0.0.0", port), AgentRequestHandler)
    print(f"Agent server listening on port {port}")
    server.serve_forever()

