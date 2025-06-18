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
# asset_handler.py (tenant-aware)
#
import os
import re
import json
import traceback
import mimetypes
from urllib.parse import unquote
from http import HTTPStatus
from pymongo import MongoClient
import gridfs

MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017")
MONGO_DB  = os.getenv("MONGO_DB", "ethel_files")

_client = MongoClient(MONGO_URI)
_db     = _client[MONGO_DB]
_fs     = gridfs.GridFS(_db)


def handle_upload(handler):
    try:
        ctype = handler.headers.get_content_type()
        if not ctype.startswith("multipart/form-data"):
            return _error(handler, HTTPStatus.BAD_REQUEST,
                          {"error": "Expected multipart/form-data"})

        boundary = handler.headers.get_boundary().encode("utf-8")
        length   = int(handler.headers.get("Content-Length", 0))
        raw      = handler.rfile.read(length)
        parts    = raw.split(b"--" + boundary)

        tenant      = None
        collection  = None
        file_path   = None
        filename    = None
        file_bytes  = None

        for part in parts:
            if b'Content-Disposition' not in part:
                continue
            headers, body = part.split(b"\r\n\r\n", 1)
            body = body.rsplit(b"\r\n", 1)[0]
            disp = headers.decode()
            if 'name="tenant"' in disp:
                tenant = body.decode().strip()
            elif 'name="collection"' in disp:
                collection = body.decode().strip()
            elif 'name="path"' in disp:
                file_path = body.decode().strip()
            elif 'name="file"' in disp:
                m = re.search(r'filename="([^"]+)"', disp)
                filename   = m.group(1)
                file_bytes = body

        if not all([tenant, collection, file_path, file_bytes]):
            return _error(handler, HTTPStatus.BAD_REQUEST, {
                "error": "Fields 'tenant','collection','path','file' required"
            })

        # Delete any old versions for this tenant/collection/path
        for doc in _db["fs.files"].find({
            "metadata.tenant":     tenant,
            "metadata.collection": collection,
            "metadata.path":       file_path
        }):
            _fs.delete(doc["_id"])

        fid = _fs.put(
            file_bytes,
            filename=filename,
            metadata={
                "tenant":     tenant,
                "collection": collection,
                "path":       file_path
            }
        )

        return _json_response(handler, HTTPStatus.OK, {"file_id": str(fid)})

    except Exception:
        traceback.print_exc()
        return _error(handler, HTTPStatus.INTERNAL_SERVER_ERROR,
                      {"error": "Upload failed"})


def handle_get_files(handler):
    # URL: GET /files[/<tenant>[/<collection>[/<path>]]]
    path     = unquote(handler.path[len("/files"):]).lstrip("/")
    segments = [s for s in path.split("/") if s]

    # 1) No segments → list tenants
    if not segments:
        tenants = _db["fs.files"].distinct("metadata.tenant")
        out = [{"type": "tenant", "name": t} for t in tenants]
        return _json_response(handler, HTTPStatus.OK, out)

    tenant = segments[0]

    # 2) Only tenant → list collections
    if len(segments) == 1:
        cols = _db["fs.files"].distinct(
            "metadata.collection",
            {"metadata.tenant": tenant}
        )
        out = [{"type": "collection", "name": c} for c in cols]
        return _json_response(handler, HTTPStatus.OK, out)

    collection = segments[1]
    subpath    = "/".join(segments[2:])  # could be file or dir

    # 3) If subpath present → attempt file download
    if subpath:
        try:
            gf = _fs.get_last_version(metadata={
                "tenant":     tenant,
                "collection": collection,
                "path":       subpath
            })
            data = gf.read()
            mime = mimetypes.guess_type(gf.filename)[0] or "application/octet-stream"
            handler.send_response(HTTPStatus.OK)
            handler.send_header("Content-Type", mime)
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return
        except gridfs.NoFile:
            return _error(handler, HTTPStatus.NOT_FOUND,
                          {"error": f"File not found: {tenant}/{collection}/{subpath}"})
        except Exception:
            traceback.print_exc()
            return _error(handler, HTTPStatus.INTERNAL_SERVER_ERROR,
                          {"error": "Error retrieving file"})

    # 4) Directory listing under this tenant+collection
    docs = list(_db["fs.files"].find({
        "metadata.tenant":     tenant,
        "metadata.collection": collection
    }))
    if not docs:
        return _error(handler, HTTPStatus.NOT_FOUND,
                      {"error": "Collection not found"})

    all_paths = [d["metadata"]["path"] for d in docs]
    listing   = _make_listing(all_paths, prefix="")
    return _json_response(handler, HTTPStatus.OK, listing)


def _make_listing(all_paths, prefix):
    seen = set()
    out  = []
    for p in all_paths:
        if prefix:
            if not p.startswith(prefix + "/"):
                continue
            tail = p[len(prefix) + 1:]
        else:
            tail = p
        first, *rest = tail.split("/", 1)
        if first in seen:
            continue
        seen.add(first)
        if rest:
            out.append({"type": "directory", "name": first})
        else:
            out.append({"type": "file",      "name": first})
    return out


def _json_response(handler, status, obj):
    body = json.dumps(obj).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _error(handler, status, payload):
    return _json_response(handler, status, payload)

