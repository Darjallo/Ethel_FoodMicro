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

def test_agent_node(state):
    """
    Calls the test_agent microservice, streams per-char deltas,
    then yields the final result.
    """
    url = "http://test_agent:8000/"
    payload = {
        "context": state.get("context"),
        "session": state.get("session"),
        "query": state.get("query"),
        "stream": state.get("stream", False)
    }

    if payload["stream"]:
        # 1) side-channel: get per-char streaming
        resp = requests.post(url, json=payload, stream=True, timeout=60)
        resp.raise_for_status()

        full = []
        # read raw bytes (chars)
        for byte in resp.iter_content(chunk_size=1):
            if not byte:
                continue
            ch = byte.decode("utf-8", errors="replace")
            full.append(ch)
            yield {"test_agent_result": {"delta": ch}}

        # 2) once done, fetch the non-streaming JSON for metadata
        meta = requests.post(url, json={**payload, "stream": False}, timeout=10).json()
        yield {
            "test_agent_result": {
                "output": "".join(full),
                "result": meta
            }
        }

    else:
        # non-streaming: just return final
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        yield {"test_agent_result": {"output": "", "result": resp.json()}}

