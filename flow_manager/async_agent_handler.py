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
"""
Asynchronous-agent callback handler for Ethel.

POST /async_agent  with JSON { "run_id": "...", "result": {...} }
---------------------------------------------------------------
• Immediately stores `result` in flow_runs (status → resumed).
• Pushes run_id on an in-process queue.
• A background worker dequeues run_id, loads the saved state, calls the
  flow’s resume(state, next_node), and finally stores any
  state["feedback"] back into the flow_runs document (status → done).

Swap the in-process queue with Redis/Celery for multi-pod production.
"""

import json, queue, threading, importlib, traceback, copy, os
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pymongo import MongoClient
from flow_resume import runs   # flow_runs collection created in flow_resume.py


# ═══════════════ queue + worker ════════════════════════════════
resume_q: "queue.Queue[str]" = queue.Queue()

def _resume_worker():
    while True:
        run_id = resume_q.get()
        try:
            # Atomically claim the run for processing
            run_doc = runs.find_one_and_update(
                {"_id": run_id, "status": "resumed"},
                {"$set": {"status": "running"}}
            )
            if run_doc:
                _resume_run(run_doc)
        except Exception:
            traceback.print_exc()
        finally:
            resume_q.task_done()

def _resume_run(run_doc: dict):
    try:
        mod   = importlib.import_module(f"flows.{run_doc['flow']}")
        state = copy.deepcopy(run_doc["state"])
        next_node = run_doc["next_node"]

        if "async_result" in run_doc:
            state["async_result"] = run_doc["async_result"]

        # capture returned final state
        final_state = mod.resume(state, next_node)

        runs.update_one(
            {"_id": run_doc["_id"]},
            {"$set": {
                "status":   "done",
                "updated":  datetime.utcnow(),
                "feedback": final_state.get("feedback")  # ← now present
            }}
        )
    except Exception as exc:
        traceback.print_exc()
        runs.update_one(
            {"_id": run_doc["_id"]},
            {"$set": {
                "status": "error",
                "error":  str(exc),
                "updated": datetime.utcnow()
            }}
        )

# Start one worker thread (change to pool if needed)
threading.Thread(target=_resume_worker, daemon=True).start()


# ═══════════════ HTTP entrypoint ═══════════════════════════════
def handle_async_agent(req: BaseHTTPRequestHandler):
    """
    Expected JSON body:
        { "run_id": "uuid", "result": {... arbitrary payload ...} }
    """
    try:
        length  = int(req.headers.get("Content-Length", 0))
        payload = json.loads(req.rfile.read(length))
        run_id  = payload["run_id"]
        result  = payload.get("result", {})
    except Exception:
        return _err(req, 400, {"error": "Invalid JSON"})

    # Store async result & flip status to resumed
    doc = runs.find_one_and_update(
        {"_id": run_id, "status": "waiting_async"},
        {"$set": {
            "status":       "resumed",
            "async_result": result,
            "updated":      datetime.utcnow()
        }}
    )
    if not doc:
        return _err(req, 404, {"error": "run_id not in waiting_async"})

    resume_q.put(run_id)            # background resume

    _ok(req, {"status": "accepted", "run_id": run_id})


# ═══════════════ small helpers ════════════════════════════════
def _ok(req, payload):
    body = json.dumps(payload).encode()
    req.send_response(202)
    req.send_header("Content-Type", "application/json")
    req.send_header("Content-Length", str(len(body)))
    req.end_headers()
    req.wfile.write(body)

def _err(req, code, payload):
    body = json.dumps(payload).encode()
    req.send_response(code)
    req.send_header("Content-Type", "application/json")
    req.send_header("Content-Length", str(len(body)))
    req.end_headers()
    req.wfile.write(body)

