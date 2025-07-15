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
# agent_pool/agents/reasoning_completion/agent.py

import os
import json
import base64
import mimetypes
from datetime import datetime
from typing import Any, Dict, List, Generator, Optional

import requests
import gridfs
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from ethelflow.agents.base_agent_server import run_server


class ReasoningCompletionAgent:
    """
    1) Accepts:
       {
         "messages": [ { "role": "...", "content": "..." }, … ],
         "file_ids": [ "tenant/collection/path/to/image.ext", … ],
         "stream": <bool>,
         "tenant": tenant,
         "reasoning_effort": <"minimal"|"moderate"|"maximal"> (optional),
         "schema": { … }  (optional),
       }
    2) Fetches each file_id from GridFS, encodes as base64, infers mime‐type.
    3) Transforms the **last** user‐message into an array of content blocks:
       [
         { "type": "text",     "text": "<original‐prompt>" },
         { "type": "image_url", "image_url": { "url": "<data:...>" } },
         …  (one block per file)
       ]
    4) Sends a single request to Azure’s /chat/completions endpoint.
       - If stream=False: returns Azure’s entire JSON blob in “response”.
       - If stream=True: relays each SSE chunk back as JSON lines.
    """

    def __init__(self):
        # 1) MongoDB/GridFS setup
        MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017")
        MONGO_DB = os.getenv("MONGO_DB", "ethel_files")
        try:
            self.mongo_client = MongoClient(MONGO_URI)
            self.mongo_db = self.mongo_client[MONGO_DB]
            self.fs = gridfs.GridFS(self.mongo_db)
        except PyMongoError as e:
            raise RuntimeError(f"Could not connect to MongoDB: {e}")

        # 2) Azure OpenAI Chat config
        endpoint = os.getenv("AZURE_ENDPOINT", "").rstrip("/")
        if not endpoint:
            raise RuntimeError(
                "Environment variable AZURE_ENDPOINT is missing or empty"
            )
        self.azure_endpoint = endpoint

        self.azure_key = os.getenv("AZURE_KEY")
        if not self.azure_key:
            raise RuntimeError("Environment variable AZURE_KEY is missing or empty")

        self.azure_deployment = os.getenv("AZURE_CHAT_DEPLOYMENT")
        if not self.azure_deployment:
            raise RuntimeError(
                "Environment variable AZURE_CHAT_DEPLOYMENT is missing or empty"
            )

        self.api_version = os.getenv("AZURE_API_VERSION", "2025-04-01-preview")

        # Build the correct URL _without_ a double slash
        self.chat_url = (
            f"{self.azure_endpoint}/openai/deployments/"
            f"{self.azure_deployment}/chat/completions"
            f"?api-version={self.api_version}"
        )

        self.headers = {
            "Content-Type": "application/json",
            "api-key": self.azure_key,
        }

    def _fetch_and_encode_file(self, file_id: str) -> Optional[str]:
        """
        Fetches “tenant/collection/path/to/file.ext” from GridFS, returns a data-URL string:
          "data:<mime>;base64,<b64_payload>"
        If the file doesn’t exist or an error occurs, return None.
        """
        if "/" not in file_id:
            return None

        tenant, collection_name, path = file_id.split("/", 2)
        try:
            gf = self.fs.get_last_version(
                metadata={"tenant": tenant, "collection": collection_name, "path": path}
            )
        except gridfs.NoFile:
            return None
        except Exception:
            return None

        file_bytes = gf.read()
        mime, _ = mimetypes.guess_type(path)
        if mime is None:
            mime = "application/octet-stream"

        b64 = base64.b64encode(file_bytes).decode("utf-8")
        # Prepend “data:<mime>;base64,”
        return f"data:{mime};base64,{b64}"

    def handle(self, request_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Non-streaming: one-shot Azure call. Returns a single JSON dict.
        Expects:
          {
            "messages": [ { "role": "user"|"system"|"assistant", "content": "<str>" }, … ],
            "file_ids": [ "collection/path/image.ext", … ],
            "stream": <bool>,
            "reasoning_effort": <"minimal"|"moderate"|"maximal"> (optional),
            "schema": { … }  (optional JSON schema)
          }
        """
        base_response: Dict[str, Any] = {
            "id": "reasoning_completion_response",
            "object": "task_result",
            "created": int(datetime.utcnow().timestamp()),
        }

        # 1) Validate “messages”
        raw_msgs = request_json.get("messages")
        if not isinstance(raw_msgs, list) or not all(
            isinstance(m, dict) for m in raw_msgs
        ):
            base_response.update(
                {
                    "status": 400,
                    "error": "Missing or invalid 'messages' (must be a list of {role,content} dicts).",
                }
            )
            return base_response
        messages: List[Dict[str, Any]] = raw_msgs.copy()

        # 2) Validate/collect file_ids → build list of data-URLs
        raw_file_ids = request_json.get("file_ids", [])
        dataurls: List[str] = []
        if isinstance(raw_file_ids, list):
            for fid in raw_file_ids:
                if isinstance(fid, str) and fid:
                    du = self._fetch_and_encode_file(fid)
                    if du is None:
                        base_response.update(
                            {
                                "status": 404,
                                "error": f"Could not load file '{fid}' from GridFS.",
                            }
                        )
                        return base_response
                    dataurls.append(du)

        # 3) Optional “reasoning_effort”
        reasoning_effort = request_json.get("reasoning_effort", None)
        reasoning_prefs = {}
        if reasoning_effort is not None:
            if not isinstance(
                reasoning_effort, str
            ) or reasoning_effort.lower() not in ("minimal", "moderate", "maximal"):
                base_response.update(
                    {
                        "status": 400,
                        "error": "Invalid 'reasoning_effort' (must be 'minimal','moderate','maximal').",
                    }
                )
                return base_response
            reasoning_prefs = {
                "reasoning_preferences": {"reasoning_effort": reasoning_effort.lower()}
            }

        # 4) Optional “schema”
        raw_schema = request_json.get("schema", None)
        if raw_schema is not None and not isinstance(raw_schema, dict):
            base_response.update(
                {
                    "status": 400,
                    "error": "Invalid 'schema' (must be a JSON-object/dict).",
                }
            )
            return base_response

        # 5) Inject images into the LAST user message, if any
        #    Azure’s GPT-with-Vision expects the “content” to be a list of rich blocks:
        #      [ {"type":"text","text":"…"}, {"type":"image_url","image_url":{ "url": <dataurl> }} , … ]
        if dataurls:
            # Find the index of the last “user” message
            user_indexes = [
                i for i, m in enumerate(messages) if m.get("role") == "user"
            ]
            if not user_indexes:
                base_response.update(
                    {
                        "status": 400,
                        "error": "Cannot attach images: no user message found.",
                    }
                )
                return base_response

            last_user_idx = user_indexes[-1]
            orig_content = messages[last_user_idx].get("content", "")
            if not isinstance(orig_content, str):
                orig_content = ""  # coerce to empty string

            # Build a new content array:
            rich_content = []
            # (a) first block: the original text
            rich_content.append({"type": "text", "text": orig_content})
            # (b) then one block per data-URL
            for du in dataurls:
                rich_content.append({"type": "image_url", "image_url": {"url": du}})

            # Overwrite that message’s “content” with the array
            messages[last_user_idx]["content"] = rich_content

        # 6) Build final payload
        payload: Dict[str, Any] = {"messages": messages}
        if reasoning_prefs:
            payload.update(reasoning_prefs)
        if raw_schema is not None:
            payload["schema"] = raw_schema

        # 7) Send to Azure (non-streaming)
        try:
            resp = requests.post(
                self.chat_url, headers=self.headers, json=payload, timeout=120
            )
            resp.raise_for_status()
        except requests.exceptions.HTTPError as http_err:
            try:
                err_body = resp.json()
            except Exception:
                err_body = resp.text
            base_response.update(
                {
                    "status": 500,
                    "error": f"Azure request failed: {http_err} → {err_body}",
                }
            )
            return base_response
        except Exception as e:
            base_response.update(
                {"status": 500, "error": f"Error sending request to Azure: {e}"}
            )
            return base_response

        # 8) Return Azure’s JSON response directly
        azure_body = resp.json()
        base_response.update({"status": 200, "response": azure_body})
        return base_response

    def stream(self, request_json: Dict[str, Any]) -> Generator[bytes, None, None]:
        """
        Streaming (SSE) entrypoint. Mirrors the same logic as handle(...), but
        passes stream=True to Azure and relays each SSE chunk back to the client.
        """
        base_response: Dict[str, Any] = {
            "id": "reasoning_completion_response",
            "object": "task_result",
            "created": int(datetime.utcnow().timestamp()),
        }

        # 1) Validate “messages”
        raw_msgs = request_json.get("messages")
        if not isinstance(raw_msgs, list) or not all(
            isinstance(m, dict) for m in raw_msgs
        ):
            err = {
                **base_response,
                "status": 400,
                "error": "Missing or invalid 'messages' (must be list of {role,content}).",
            }
            chunk = json.dumps(err).encode("utf-8")
            size = f"{len(chunk):X}\r\n".encode("utf-8")
            yield size + chunk + b"\r\n"
            return

        messages: List[Dict[str, Any]] = raw_msgs.copy()

        # 2) Collect file_ids → data URLs
        raw_file_ids = request_json.get("file_ids", [])
        dataurls: List[str] = []
        if isinstance(raw_file_ids, list):
            for fid in raw_file_ids:
                if isinstance(fid, str) and fid:
                    du = self._fetch_and_encode_file(fid)
                    if du is None:
                        err = {
                            **base_response,
                            "status": 404,
                            "error": f"Could not load file '{fid}' from GridFS.",
                        }
                        chunk = json.dumps(err).encode("utf-8")
                        size = f"{len(chunk):X}\r\n".encode("utf-8")
                        yield size + chunk + b"\r\n"
                        return
                    dataurls.append(du)

        # 3) Optional reasoning_effort
        reasoning_effort = request_json.get("reasoning_effort", None)
        reasoning_prefs: Dict[str, Any] = {}
        if reasoning_effort is not None:
            if not isinstance(
                reasoning_effort, str
            ) or reasoning_effort.lower() not in ("minimal", "moderate", "maximal"):
                err = {
                    **base_response,
                    "status": 400,
                    "error": "Invalid 'reasoning_effort' (must be 'minimal','moderate','maximal').",
                }
                chunk = json.dumps(err).encode("utf-8")
                size = f"{len(chunk):X}\r\n".encode("utf-8")
                yield size + chunk + b"\r\n"
                return
            reasoning_prefs = {
                "reasoning_preferences": {"reasoning_effort": reasoning_effort.lower()}
            }

        # 4) Optional schema
        raw_schema = request_json.get("schema", None)
        if raw_schema is not None and not isinstance(raw_schema, dict):
            err = {
                **base_response,
                "status": 400,
                "error": "Invalid 'schema' (must be a JSON-object/dict).",
            }
            chunk = json.dumps(err).encode("utf-8")
            size = f"{len(chunk):X}\r\n".encode("utf-8")
            yield size + chunk + b"\r\n"
            return

        # 5) Inject images into the last user message
        if dataurls:
            user_idxs = [i for i, m in enumerate(messages) if m.get("role") == "user"]
            if not user_idxs:
                err = {
                    **base_response,
                    "status": 400,
                    "error": "Cannot attach images: no user message found.",
                }
                chunk = json.dumps(err).encode("utf-8")
                size = f"{len(chunk):X}\r\n".encode("utf-8")
                yield size + chunk + b"\r\n"
                return

            last_user_idx = user_idxs[-1]
            orig_content = messages[last_user_idx].get("content", "")
            if not isinstance(orig_content, str):
                orig_content = ""

            rich_content: List[Dict[str, Any]] = []
            rich_content.append({"type": "text", "text": orig_content})
            for du in dataurls:
                rich_content.append({"type": "image_url", "image_url": {"url": du}})

            messages[last_user_idx]["content"] = rich_content

        # 6) Build final payload
        payload: Dict[str, Any] = {"messages": messages}
        if reasoning_prefs:
            payload.update(reasoning_prefs)
        if raw_schema is not None:
            payload["schema"] = raw_schema

        # 7) Call Azure with stream=True
        try:
            resp = requests.post(
                self.chat_url,
                headers=self.headers,
                json=payload,
                timeout=300,
                stream=True,
            )
            resp.raise_for_status()
        except requests.exceptions.HTTPError as http_err:
            try:
                err_body = resp.json()
            except Exception:
                err_body = resp.text
            err = {
                **base_response,
                "status": 500,
                "error": f"Azure request failed: {http_err} → {err_body}",
            }
            chunk = json.dumps(err).encode("utf-8")
            size = f"{len(chunk):X}\r\n".encode("utf-8")
            yield size + chunk + b"\r\n"
            return
        except Exception as e:
            err = {
                **base_response,
                "status": 500,
                "error": f"Error sending request to Azure: {e}",
            }
            chunk = json.dumps(err).encode("utf-8")
            size = f"{len(chunk):X}\r\n".encode("utf-8")
            yield size + chunk + b"\r\n"
            return

        # 8) Relay each SSE “data: {...}” line back to the Flow Manager
        for raw_line in resp.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            try:
                prefix = b"data: "
                if raw_line.startswith(prefix):
                    payload_bytes = raw_line[len(prefix) :]
                    if payload_bytes.strip() == b"[DONE]":
                        break
                    chunk_obj = json.loads(payload_bytes.decode("utf-8"))
                    to_send = chunk_obj
                else:
                    continue
            except Exception:
                continue

            chunk_json = json.dumps({"choices": [to_send]}).encode("utf-8")
            size = f"{len(chunk_json):X}\r\n".encode("utf-8")
            yield size + chunk_json + b"\r\n"

        # 9) After “[DONE]”, send a final done‐signal
        done_msg = json.dumps({"choices": [{"delta": {"done": True}}]}).encode("utf-8")
        size = f"{len(done_msg):X}\r\n".encode("utf-8")
        yield size + done_msg + b"\r\n"

    # END of stream()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    run_server(port=port, handler_instance=ReasoningCompletionAgent())
