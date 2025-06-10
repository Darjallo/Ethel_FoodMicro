# Project Ethel
# Handler for freeze/thaw of asynchronous tasks (mainly human-in-the-loop)
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
# async_agent_handler.py
#
import json
from flow_resume import mark_task_done  # your helper that flips run -> resumed

def handle_async_agent(req):
    """
    Expected JSON:
      {
        "task_id": "...",
        "run_id":  "...",
        "result":  {...}       # arbitrary payload from human/async agent
      }
    """
    try:
        length = int(req.headers.get("Content-Length", 0))
        body   = req.rfile.read(length)
        data   = json.loads(body)
    except Exception:
        return _error(req, 400, {"error": "Invalid JSON"})

    # TODO: validation
    task_id = data.get("task_id")
    run_id  = data.get("run_id")
    result  = data.get("result", {})

    # write result & resume the flow run
    mark_task_done(task_id, run_id, result)

    req.send_response(200)
    req.send_header("Content-Type", "application/json")
    body = json.dumps({"status":"accepted"}).encode("utf-8")
    req.send_header("Content-Length", str(len(body)))
    req.end_headers()
    req.wfile.write(body)

def _error(req, code, payload):
    body = json.dumps(payload).encode("utf-8")
    req.send_response(code)
    req.send_header("Content-Type", "application/json")
    req.send_header("Content-Length", str(len(body)))
    req.end_headers()
    req.wfile.write(body)

