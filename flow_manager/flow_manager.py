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
# flow_manager/flow_manager.py

import os
import re
import ssl
import json
import traceback
import importlib
import cgi

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pymongo import MongoClient
import gridfs

SSL_PORT = int(os.getenv("SSL_PORT", "8000"))
SSL_CERT = os.getenv("SSL_CERT_PATH")
SSL_KEY  = os.getenv("SSL_KEY_PATH")

# Mongo settings (override with your env vars as needed)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017")
MONGO_DB  = os.getenv("MONGO_DB", "ethel_files")

# initialize Mongo + GridFS
_mongo_client = MongoClient(MONGO_URI)
_mongo_db     = _mongo_client[MONGO_DB]
_fs           = gridfs.GridFS(_mongo_db)


class FlowManagerRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/upload":
            return self._handle_upload()

        # --- otherwise: the normal / POST for flows ---
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            return self._error(400, {"error": "Invalid JSON"})

        flow = req.get("flow")
        if not flow or not re.fullmatch(r"[A-Za-z0-9_]+", flow):
            return self._error(400, {"error": "Missing or invalid flow name"})

        try:
            mod = importlib.import_module(f"flows.{flow}")
        except ImportError:
            return self._error(404, {"error": f"No such flow '{flow}'"})

        try:
            if req.get("stream"):
                self._handle_streaming(mod, req)
            else:
                self._handle_non_stream(mod, req)
        except Exception:
            traceback.print_exc()
            self._error(500, {"error": "Internal server error"})

    def _handle_upload(self):
        """Handle multipart/form-data POST to /upload"""
        ctype, pdict = cgi.parse_header(self.headers.get('Content-Type', ''))
        if ctype != 'multipart/form-data':
            return self._error(400, {"error": "Expected multipart/form-data"})

        fs = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                'REQUEST_METHOD':'POST',
                'CONTENT_TYPE':self.headers['Content-Type'],
            },
            keep_blank_values=True
        )

        # required fields
        fileitem   = fs['file'] if 'file' in fs else None
        collection  = fs.getvalue('collection')
        file_path  = fs.getvalue('path')

# explicit None check for FieldStorage
        if fileitem is None or not collection or not file_path:
            return self._error(400, {"error": "Fields 'file', 'collection' and 'path' required"})

        # remove any existing versions
        existing = _mongo_db.fs.files.find({
            "metadata.collection": collection,
            "metadata.path":      file_path
        })
        for doc in existing:
            _fs.delete(doc['_id'])

        # read and store
        data = fileitem.file.read()
        new_id = _fs.put(
            data,
            filename=fileitem.filename,
            metadata={"collection": collection, "path": file_path}
        )

        resp = {"file_id": str(new_id)}
        body = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_streaming(self, mod, req):
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Transfer-Encoding","chunked")
        self.end_headers()

        for update in mod.run(
            req["context"],
            req.get("query", {}),
            stream=True
        ):
            chunk = (json.dumps(update) + "\n").encode("utf-8")
            self._send_chunk(chunk)

        # terminator
        self._send_chunk(b"", end=True)

    def _handle_non_stream(self, mod, req):
        gen   = mod.run(req["context"], req.get("query", {}), stream=False)
        first = next(gen, {})
        body  = json.dumps(first).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_chunk(self, data: bytes, end: bool = False):
        if end:
            self.wfile.write(b"0\r\n\r\n")
        else:
            size = f"{len(data):X}\r\n".encode("utf-8")
            self.wfile.write(size + data + b"\r\n")
        self.wfile.flush()

    def _error(self, code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)


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

