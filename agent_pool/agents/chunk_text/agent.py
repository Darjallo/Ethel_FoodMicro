# Project Ethel
# Agent for semantic chunking of text
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
from datetime import datetime
from typing import Any, Dict, List

from langchain.text_splitter import RecursiveCharacterTextSplitter
from agent_pool.base_agent_server import run_server


class ChunkTextAgent:
    """
    Agent that:
      1. Accepts { "text": <string> } in the request JSON.
      2. Splits that text into chunks (via RecursiveCharacterTextSplitter).
      3. Returns JSON:
           {
             "id": "chunk_text_response",
             "object": "task_result",
             "created": <timestamp>,
             "status": 200,
             "chunks": [ <chunk1>, <chunk2>, … ]
           }
      or an error payload on failure.
    """

    def __init__(self):
        # Read chunk‐size parameters (with sensible defaults):
        try:
            self.chunk_size = int(os.getenv("CHUNK_SIZE", "2000"))
        except ValueError:
            self.chunk_size = 2000

        try:
            self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "400"))
        except ValueError:
            self.chunk_overlap = 400

    def handle(self, request_json: Dict[str, Any]) -> Dict[str, Any]:
        response: Dict[str, Any] = {
            "id":      "chunk_text_response",
            "object":  "task_result",
            "created": int(datetime.utcnow().timestamp()),
        }

        # 1) Validate “text” field
        raw = request_json.get("text")
        if not isinstance(raw, str):
            response.update({
                "status": 400,
                "error": "Missing or invalid 'text' (must be a string)."
            })
            return response

        text = raw or ""
        try:
            # 2) Instantiate a RecursiveCharacterTextSplitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                add_start_index=False,  # we only need raw strings
            )
            # 3) Split into a list of chunks
            chunks: List[str] = splitter.split_text(text)
        except Exception as e:
            traceback.print_exc()
            response.update({
                "status": 500,
                "error": f"Error during text splitting: {e}"
            })
            return response

        # 4) Success – return the list of chunk‐strings
        response.update({
            "status": 200,
            "chunks": chunks
        })
        return response


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    run_server(port=port, handler_instance=ChunkTextAgent())

