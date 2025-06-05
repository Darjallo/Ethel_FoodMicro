# Project Ethel
# Agent for ADA3large batch embedding
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
import os, time, requests, traceback
from datetime import datetime
from typing import Any, Dict, List
from agent_pool.base_agent_server import run_server

class EmbAda3LargeAgent:
    def __init__(self):
        endpoint   = os.environ["AZURE_ENDPOINT"]
        key        = os.environ["AZURE_KEY"]
        deploy     = os.environ["AZURE_ADA3LARGE_DEPLOYMENT"]
        self.url   = f"{endpoint}/openai/deployments/{deploy}/embeddings?api-version=2023-05-15"
        self.headers = {"Content-Type":"application/json", "api-key":key}
        try:
            self.batch_size = int(os.getenv("BATCH_SIZE", "10"))
        except:
            self.batch_size = 10
        try:
            self.batch_delay = float(os.getenv("BATCH_DELAY", "2"))
        except:
            self.batch_delay = 2.0

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        max_retries = 5
        backoff = 1
        for attempt in range(max_retries):
            try:
                payload = {"input": texts}
                resp = requests.post(self.url, json=payload, headers=self.headers, timeout=60)
                if resp.status_code == 429:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                resp.raise_for_status()
                data = resp.json()
                return [item["embedding"] for item in data["data"]]
            except requests.exceptions.HTTPError as http_err:
                if resp.status_code == 429:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise RuntimeError(f"HTTP {resp.status_code} during embed: {http_err}")
            except Exception as exc:
                raise RuntimeError(f"Embedding error: {exc}")
        raise RuntimeError("Exceeded max retries for batch")

    def handle(self, request_json: Dict[str, Any]) -> Dict[str, Any]:
        result = {
            "id": "emb_ada3large_response",
            "object": "task_result",
            "created": int(datetime.utcnow().timestamp()),
        }
        texts = request_json.get("texts")
        if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
            result.update({"status":400, "error":"Missing or invalid 'texts' (must be list of strings)."})
            return result
        all_embeds: List[List[float]] = []
        try:
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i : i+self.batch_size]
                batch_embeds = self.embed_batch(batch)
                all_embeds.extend(batch_embeds)
                if i + self.batch_size < len(texts):
                    time.sleep(self.batch_delay)
        except Exception as exc:
            traceback.print_exc()
            result.update({"status":500, "error": f"Embedding failed: {exc}"})
            return result

        result.update({"status":200, "embeddings": all_embeds})
        return result

if __name__ == "__main__":
    port = int(os.getenv("PORT","8000"))
    run_server(port=port, handler_instance=EmbAda3LargeAgent())

