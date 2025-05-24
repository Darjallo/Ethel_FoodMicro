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
#
import requests
import json

def test_agent_node(state):
    """
    Calls the test_agent microservice and streams response if requested.
    This node ALWAYS yields (never returns), so it is compatible with LangGraph
    whether the flow is streaming or not.
    """
    payload = {
        "context": state.get("context"),
        "session": state.get("session"),
        "query": state.get("query"),
        "stream": state.get("stream", False)
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    url = "http://test_agent:8000/"

    if payload.get("stream"):
        # Streaming mode: yield partial responses as they come in
        resp = requests.post(url, json=payload, stream=True, timeout=30)
        resp.raise_for_status()
        for chunk in resp.iter_content(chunk_size=None):
            if chunk:
                # Try to decode JSON, fallback to string if not JSON
                try:
                    data = json.loads(chunk.decode("utf-8"))
                except Exception:
                    data = chunk.decode("utf-8")
                yield {"test_agent_result": data}
    else:
        # Non-streaming: yield just once
        resp = requests.post(url, json=payload, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        yield {"test_agent_result": data}

