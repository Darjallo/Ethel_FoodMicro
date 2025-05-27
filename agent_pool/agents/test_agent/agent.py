# Project Ethel
# Test Echo Agent
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
from datetime import datetime
from agent_pool.base_agent_server import run_server

class TestAgent:
    def handle(self, request_json):
        """
        Always returns a single JSON completion echoing back the user's question.
        """
        # assume the user’s question is passed in request_json["context"]["question"]
        question = request_json.get("context", {}).get("question", "<no question>")
        content = (
            f"Pondered the question “{question}” at {datetime.now().isoformat()}"
        )
        # build an OpenAI‐style completion payload
        return {
            "id":      "test_agent_response",
            "object":  "chat.completion",
            "created": int(datetime.now().timestamp()),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop"
            }]
        }

    # no .stream() at all — any "stream" requests are just handled eagerly

if __name__ == "__main__":
    # run on port 8000 by default
    run_server(port=8000, handler_instance=TestAgent())

