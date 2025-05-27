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
    # injected at runtime
    business_logic = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"Invalid JSON"}')
            return

        # always chunked, agent itself handles streaming vs non
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        # choose agent.stream or agent.handle
        if req.get("stream") and hasattr(self.business_logic, "stream"):
            gen = self.business_logic.stream(req)
        else:
            single = self.business_logic.handle(req)
            gen = (json.dumps(single),)

        for chunk in gen:
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
            size = f"{len(chunk):X}\r\n".encode("utf-8")
            self.wfile.write(size + chunk + b"\r\n")
            self.wfile.flush()

        # end
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

def run_server(port, handler_instance):
    AgentRequestHandler.business_logic = handler_instance
    server = ThreadingHTTPServer(("0.0.0.0", port), AgentRequestHandler)
    print(f"Agent server listening on port {port}")
    server.serve_forever()

