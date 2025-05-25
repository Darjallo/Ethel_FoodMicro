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
    Streams every character as soon as it comes in, then finally yields
    the accumulated text + the full, non-streamed result for downstream.
    """
    context = state.get("context")
    session = state.get("session")
    query   = state.get("query")
    do_stream = state.get("stream", False)
    url = "http://test_agent:8000/"

    if do_stream:
        # 1) start streaming from agent, char-by-char
        resp = requests.post(
            url,
            json={"context": context, "session": session, "query": query, "stream": True},
            stream=True,
            timeout=60
        )
        resp.raise_for_status()

        full_output = ""
        # CHUNK-SIZE=1 forces each incoming byte out immediately
        for b in resp.iter_content(chunk_size=1):
            if not b:
                continue
            ch = b.decode("utf-8", errors="replace")
            full_output += ch
            # yield each character immediately
            yield {"test_agent_result": {"output": ch}}

        # 2) once the stream is done, fetch the final structured response
        final = requests.post(
            url,
            json={"context": context, "session": session, "query": query},
            timeout=30
        ).json()

        # yield the full accumulated text plus the real result
        yield {"test_agent_result": {"output": full_output, "result": final}}

    else:
        # non-stream: just one shot
        resp = requests.post(
            url,
            json={"context": context, "session": session, "query": query},
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        yield {"test_agent_result": {"output": "", "result": data}}

