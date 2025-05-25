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
import time
import json

class TestAgent:
    def handle(self, request_json):
        # Non-streaming: Echo input, add "processed" timestamp
        content = f"Processed with pride by your friendly neighborhood test agent at {datetime.now().isoformat()}"
        response = {
            "id": "test_agent_response",
            "object": "chat.completion",
            "created": int(time.time()),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content
                    },
                    "finish_reason": "stop"
                }
            ]
        }
        return response

    def stream(self, request_json):
        # Streaming: yield partial OpenAI-style responses character by character
        content = f"Processed with pride by your friendly neighborhood test agent at {datetime.now().isoformat()}"
        for char in content:
            chunk = {
                "id": "test_agent_stream",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": char
                        },
                        "finish_reason": None
                    }
                ]
            }
            print(f"Yielding: [{char}]")
            yield json.dumps(chunk)
            time.sleep(0.05)  # Adjust speed as needed
        
        # Send the final DONE message, exactly like OpenAI does
        done_chunk = {
            "id": "test_agent_stream",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }
            ]
        }
        yield json.dumps(done_chunk)

if __name__ == "__main__":
    run_server(port=8000, handler_instance=TestAgent())


