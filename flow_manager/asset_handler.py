# Handler for assets available to flows
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
# asset_handler.py

import os
import re
import json
import ssl
import mimetypes
import traceback
from urllib.parse import unquote
from pymongo import MongoClient
import gridfs
from http import HTTPStatus

# Mongo settings (override via env)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017")
MONGO_DB  = os.getenv("MONGO_DB", "ethel_files")

# init Mongo + GridFS
_mongo_client = MongoClient(MONGO_URI)
_mongo_db     = _mongo_client[MONGO_DB]
_fs           = gridfs.GridFS(_mongo_db)

def handle_upload(handler):
    try:
        ctype = handler.headers.get_content_type()
        if not ctype.startswith("multipart/form-data"):
            return _error(handler, HTTPStatus.BAD_REQUEST, {"error": "Expected multipart/form-data"})

        fs = handler.rfile
        pdict = {}
        pdict["boundary"] = handler.headers.get_boundary().encode("utf-8")
        content_length = int(handler.headers.get("Content-Length",0))
        data = fs.read(content_length)

        # manually parse: look for file and metadata fields
        # For brevity, assume we get 'file', 'collection', 'path' fields.
        # In production you might use werkzeug or cgi.FieldStorage.
        parts = data.split(b"--" + pdict["boundary"])
        file_bytes = None
        collection = None
        file_path  = None
        filename   = None

        for part in parts:
            if b'Content-Disposition' not in part:
                continue
            headers, body = part.split(b"\r\n\r\n",1)
            body = body.rsplit(b"\r\n",1)[0]
            disp = headers.decode()
            if 'name="file"' in disp:
                # extract filename
                m = re.search(r'filename="([^"]+)"', disp)
                filename = m.group(1)
                file_bytes = body
            elif 'name="collection"' in disp:
                collection = body.decode().strip()
            elif 'name="path"' in disp:
                file_path = body.decode().strip()

        if file_bytes is None or not collection or not file_path:
            return _error(handler, HTTPStatus.BAD_REQUEST,
                          {"error":"Fields 'file', 'collection', 'path' required"})

        # delete old
        for doc in _mongo_db.fs.files.find({
            "metadata.collection": collection,
            "metadata.path":      file_path
        }):
            _fs.delete(doc["_id"])

        fid = _fs.put(
            file_bytes,
            filename=filename,
            metadata={"collection": collection, "path": file_path}
        )

        resp = {"file_id": str(fid)}
        body = json.dumps(resp).encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type","application/json")
        handler.send_header("Content-Length",str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    except Exception:
        traceback.print_exc()
        return _error(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {"error":"Upload failed"})

def handle_get_files(handler):
    # GET /files[/collection/...path...]
    path = unquote(handler.path[len("/files"):]).lstrip("/")
    segments = [s for s in path.split("/") if s]

    handler.send_response(200)
    handler.send_header("Content-Type","application/json")
    handler.end_headers()

    if not segments:
        # list collections
        cols = _mongo_db.fs.files.distinct("metadata.collection")
        out = [{"type":"collection","name":c} for c in cols]
        handler.wfile.write(json.dumps(out).encode())
        return

    collection = segments[0]
    subpath = "/".join(segments[1:])

    # find directories and files at this prefix
    files = list(_mongo_db.fs.files.find({
        "metadata.collection": collection,
        "metadata.path":      {"$regex": f"^{re.escape(subpath)}"}
    }))

    # build entries map
    entries = {}
    for f in files:
        rel = f["metadata"]["path"][len(subpath):].lstrip("/")
        parts = rel.split("/")
        if len(parts)==1:
            entries.setdefault(parts[0], []).append(("file", f))
        else:
            entries.setdefault(parts[0], []).append(("dir",None))

    result = []
    for name, items in entries.items():
        if items and items[0][0]=="dir":
            result.append({"type":"directory","name":name})
        else:
            result.append({"type":"file","name":name})
    handler.wfile.write(json.dumps(result).encode())

def _error(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type","application/json")
    handler.send_header("Content-Length",str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)

