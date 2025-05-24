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

class TestAgent:
    def handle(self, request_json):
        # Non-streaming: Echo input, add "processed" timestamp
        response = dict(request_json)
        response["processed"] = datetime.now().isoformat()
        return response

    def stream(self, request_json):
        # Streaming: yield text fragments, e.g., char by char or word by word
        msg = f"Processed at {datetime.now().isoformat()}"
        # Example: word-by-word streaming (like OpenAI's tokens)
        for word in msg.split():
            yield word + " "
            time.sleep(1) 

if __name__ == "__main__":
    run_server(port=8000, handler_instance=TestAgent())

