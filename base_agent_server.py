# base_agent_server.py
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
            self.send_header('Content-Type', 'application/json')
            self.send_header('Transfer-Encoding', 'chunked')
            self.end_headers()
            # Write streamed chunks using HTTP chunked transfer
            for chunk in self.business_logic.stream(req_json):
                # Accept either dict (json) or str
                if isinstance(chunk, dict):
                    chunk = json.dumps(chunk)
                chunk_bytes = (chunk + "\n").encode("utf-8")
                # Write chunk size in hex, then the chunk, then CRLF
                self.wfile.write(b"%X\r\n" % len(chunk_bytes))
                self.wfile.write(chunk_bytes)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")  # End of chunks
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

