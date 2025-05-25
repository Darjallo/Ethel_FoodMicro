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

        # Always chunked-transfer, delegate stream logic to agent itself
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Transfer-Encoding', 'chunked')
        self.end_headers()

        # Get agent output (always yields chunks, streaming or not)
        output_gen = None
        if req_json.get("stream", False) and hasattr(self.business_logic, "stream"):
            output_gen = self.business_logic.stream(req_json)
        else:
            # Non-streaming: wrap result in a single-item generator
            single_result = self.business_logic.handle(req_json)
            output_gen = (json.dumps(single_result),)

        # Stream the agent-generated output chunk by chunk
        for chunk in output_gen:
            if not isinstance(chunk, bytes):
                chunk = chunk.encode("utf-8")
            # Write chunk size in hex, then chunk, then flush
            self.wfile.write(b"%X\r\n" % len(chunk))
            self.wfile.write(chunk)
            self.wfile.write(b"\r\n")
            self.wfile.flush()

        # Signal end-of-chunks
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

def run_server(port, handler_instance):
    AgentRequestHandler.business_logic = handler_instance
    server = ThreadingHTTPServer(("0.0.0.0", port), AgentRequestHandler)
    print(f"Agent server listening on port {port}")
    server.serve_forever()

