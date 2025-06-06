# Project Ethel
# Agent for reasoning chat completion
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
import os
import traceback
import base64
import json
import filetype
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
import gridfs
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from agent_pool.base_agent_server import run_server


class ReasoningCompletionAgent:
    """
    Agent that proxies to an Azure OpenAI “chat” deployment (o4-mini), supporting:
      - OpenAI‐style `messages: [{role, content}, …]`
      - Optional `schema` (JSON Schema for structured output)
      - Optional `reasoning_effort`
      - Optional `file_ids` (list of strings: "collection/path/to/file.ext") → fetched from MongoDB/GridFS,
        base64‐encoded, and forwarded to Azure as “files”
      - `stream: bool` to toggle streaming mode

    ENV variables:
      - AZURE_ENDPOINT               → e.g. "https://my-azure-endpoint.openai.azure.com"
      - AZURE_KEY                    → your Azure OpenAI API key
      - AZURE_CHAT_DEPLOYMENT        → the name of your o4-mini deployment
      - AZURE_API_VERSION            → e.g. "2025-04-01-preview"
      - MONGO_URI                    → e.g. "mongodb://mongodb:27017"
      - MONGO_DB                     → e.g. "ethel_files"
    """

    def __init__(self):
        # === 1) Azure/OpenAI config ===
        self.azure_endpoint = os.environ["AZURE_ENDPOINT"]
        self.azure_key = os.environ["AZURE_KEY"]
        self.deployment = os.environ["AZURE_CHAT_DEPLOYMENT"]
        self.api_version = os.getenv("AZURE_API_VERSION", "2025-04-01-preview")
        self.base_url = (
            f"{self.azure_endpoint}/openai/deployments/"
            f"{self.deployment}/chat/completions?api-version={self.api_version}"
        )
        self.headers = {
            "Content-Type": "application/json",
            "api-key": self.azure_key,
        }

        # === 2) Mongo/GridFS setup ===
        mongo_uri = os.getenv("MONGO_URI", "mongodb://mongodb:27017")
        mongo_db_name = os.getenv("MONGO_DB", "ethel_files")
        try:
            self.mongo_client = MongoClient(mongo_uri)
            self.mongo_db = self.mongo_client[mongo_db_name]
            self.fs = gridfs.GridFS(self.mongo_db)
        except PyMongoError as e:
            raise RuntimeError(f"Could not connect to MongoDB: {e}")

    def _fetch_and_encode_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Given a file_id of the form "collection/path/to/file.ext", retrieve the latest version
        from GridFS, base64‐encode it, detect its MIME type (via filetype), and return:
           { "filename": "<basename>", "file": "<base64str>", "mime_type": "<mime>" }
        or None if anything goes wrong.
        """
        if "/" not in file_id:
            return None

        collection_name, path = file_id.split("/", 1)
        try:
            gf = self.fs.get_last_version(metadata={"collection": collection_name, "path": path})
            raw_bytes = gf.read()
            filename = gf.filename or os.path.basename(path)
        except Exception:
            return None

        # Detect MIME
        kind = filetype.guess(raw_bytes)
        mime = kind.mime if kind else "application/octet-stream"

        b64 = base64.b64encode(raw_bytes).decode("utf-8")
        return {"filename": filename, "file": b64, "mime_type": mime}

    def _build_payload(self, request_json: Dict[str, Any]) -> Tuple[Dict[str, Any], int, Optional[List[Dict[str, Any]]]]:
        """
        Extract and validate fields from request_json. Returns:
          - payload_for_azure: the dict we will send to Azure
          - http_status: 200 if OK, or 400 on validation error
          - error_list: if http_status != 200, a one‐element list of {"error": "..."} for client
        """
        # Base response template
        err = None
        payload: Dict[str, Any] = {}

        # 1) `messages` (required, list of role/content dicts)
        msgs = request_json.get("messages")
        if not isinstance(msgs, list) or not all(isinstance(m, dict) for m in msgs):
            return {}, 400, [{"error": "Missing or invalid 'messages' (must be a list of {role,content} dicts)."}]
        payload["messages"] = msgs  # pass through verbatim

        # 2) optional `schema`
        schema = request_json.get("schema")
        if schema is not None:
            # client can pass a JSON Schema dict or string. We forward under "json_schema".
            if isinstance(schema, (dict, str)):
                payload["json_schema"] = schema
            else:
                return {}, 400, [{"error": "Invalid 'schema' (must be a dict or string)."}]

        # 3) optional `reasoning_effort`
        effort = request_json.get("reasoning_effort")
        if effort is not None:
            try:
                effort_val = int(effort)
                payload["reasoning_effort"] = effort_val
            except Exception:
                return {}, 400, [{"error": "Invalid 'reasoning_effort' (must be an integer)."}]

        # 4) optional `file_ids`
        file_ids = request_json.get("file_ids", [])
        files_list: List[Dict[str, Any]] = []
        if file_ids is not None:
            if not isinstance(file_ids, list) or not all(isinstance(f, str) for f in file_ids):
                return {}, 400, [{"error": "Invalid 'file_ids' (must be a list of strings)."}]
            # For each file_id, fetch and encode
            for fid in file_ids:
                pkt = self._fetch_and_encode_file(fid)
                if pkt:
                    files_list.append(pkt)
            if files_list:
                payload["files"] = files_list

        return payload, 200, None

    def handle(self, request_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Non‐streaming entry point. Returns a single JSON dict with Azure's full response.
        """
        base_resp: Dict[str, Any] = {
            "id":      "reasoning_completion_response",
            "object":  "task_result",
            "created": int(datetime.utcnow().timestamp()),
        }

        # Validate + build payload
        payload, status, error_list = self._build_payload(request_json)
        if status != 200:
            base_resp.update({"status": 400, "error": error_list[0]["error"]})
            return base_resp

        # 5) Call Azure (non-stream)
        try:
            resp = requests.post(self.base_url, json=payload, headers=self.headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            traceback.print_exc()
            base_resp.update({"status": 500, "error": f"Azure request failed: {e}"})
            return base_resp

        # 6) Return full body under “choices” (mimicking ChatCompletion)
        base_resp.update({"status": 200, **data})
        return base_resp

    def stream(self, request_json: Dict[str, Any]) -> Any:
        """
        Streaming‐mode entry point. Yields one JSON chunk at a time as Azure returns choices.
        """
        # 1) Build + validate payload
        payload, status, error_list = self._build_payload(request_json)
        if status != 200:
            yield {"id":"reasoning_completion_response","object":"task_result",
                   "created":int(datetime.utcnow().timestamp()),
                   "status":400,"error":error_list[0]["error"]}
            return

        # 2) Tell Azure we want a stream
        payload["stream"] = True

        try:
            resp = requests.post(self.base_url, json=payload, headers=self.headers, timeout=120, stream=True)
            resp.raise_for_status()
        except Exception as e:
            traceback.print_exc()
            yield {"id":"reasoning_completion_response","object":"task_result",
                   "created":int(datetime.utcnow().timestamp()),
                   "status":500,"error":f"Azure request failed: {e}"}
            return

        # 3) Iterate over Azure’s chunked response lines
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            # Each line is typically “data: <json>” or just a JSON blob
            stripped = line.decode() if isinstance(line, bytes) else line
            if stripped.startswith("data:"):
                stripped = stripped[len("data:"):].strip()

            try:
                chunk_json = json.loads(stripped)
            except Exception:
                # skip any non-JSON lines
                continue

            yield chunk_json  # forward each chunk as‐is

        # 4) Final “done” marker (optional)
        yield {"id":"reasoning_completion_response","object":"task_result",
               "created":int(datetime.utcnow().timestamp()),
               "status":200,"choices":[]}

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    run_server(port=port, handler_instance=ReasoningCompletionAgent())

