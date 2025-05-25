# Project Ethel
# Node adapter for test echo agent, needs to be included in nodes.py
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
import requests
import json

def test_agent_node(state):
    """
    Streams JSON‐chunks from test_agent, extracts single-character deltas,
    yields {"test_agent_result":{"delta":<char>}} on each, then a final
    {"test_agent_result":{"output":<full_text>,"result":<meta>}}.
    """
    payload = {
        "context": state.get("context"),
        "session": state.get("session"),
        "query":   state.get("query"),
        "stream":  state.get("stream", False)
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    url = "http://test_agent:8000/"

    if payload.get("stream", False):
        resp = requests.post(url, json=payload, stream=True, timeout=60)
        resp.raise_for_status()

        full_text = ""
        buffer = ""
        decoder = json.JSONDecoder()

        for chunk in resp.iter_content(chunk_size=None):
            if not chunk:
                continue
            buffer += chunk.decode("utf-8", errors="replace")
            # pull out as many complete JSON objects as we can
            while True:
                try:
                    obj, idx = decoder.raw_decode(buffer)
                except ValueError:
                    break
                buffer = buffer[idx:].lstrip()
                # extract the new token
                delta = (
                    obj
                    .get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content", "")
                )
                if delta:
                    # yield single-character deltas
                    for c in delta:
                        full_text += c
                        yield {"test_agent_result": {"delta": c}}

        # stream done, now fetch the full metadata
        meta_resp = requests.post(
            url,
            json={**payload, "stream": False},
            timeout=10
        )
        meta_resp.raise_for_status()
        meta = meta_resp.json()

        # final yield: the assembled text plus metadata
        yield {
            "test_agent_result": {
                "output": full_text,
                "result": meta
            }
        }

    else:
        # non-streaming: just do one-shot, no deltas
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        yield {
            "test_agent_result": {
                "output": "",
                "result": data
            }
        }

