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
Handle callbacks from humans or other async agents.  The callback payload
contains a run_id; we load the frozen run from Mongo, inject the async result,
and resume the flow immediately in a background thread—no polling loop
required.
"""
import json, threading, importlib, traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pymongo import MongoClient
import os


# --- DB setup ----------------------------------------------------
mongo = MongoClient(os.getenv("MONGO_URI", "mongodb://mongodb:27017"))
db    = mongo[os.getenv("MONGO_DB",  "ethel_files")]
runs  = db.flow_runs        # same collection used by flow_resume.save_run()


# --- main entry --------------------------------------------------
def handle_async_agent(req: BaseHTTPRequestHandler):

    try:
        data = json.loads(req.rfile.read(int(req.headers.get("Content-Length", 0))))
        run_id  = data["run_id"]
        result  = data.get("result", {})
    except Exception:
        return _error(req, 400, {"error": "Invalid JSON or missing run_id"})

    # Atomically fetch & mark as running
    run_doc = runs.find_one_and_update(
        {"_id": run_id, "status": "waiting_async"},
        {"$set": {"status": "running", "async_result": result,
                  "updated": datetime.utcnow()}}
    )
    if not run_doc:
        return _error(req, 404, {"error": f"run_id '{run_id}' not found or already resumed"})

    # Resume in background so we can 200-OK immediately
    threading.Thread(target=_resume_run, args=(run_doc,), daemon=True).start()

    _ok(req, {"status": "accepted", "run_id": run_id})


# --- resume helper ----------------------------------------------
def _resume_run(run_doc: dict):
    try:
        mod   = importlib.import_module(f"flows.{run_doc['flow']}")
        state = run_doc["state"]
        # Inject the async_result so downstream nodes can read it
        state["async_result"] = run_doc.get("async_result")

        next_node = run_doc["next_node"]
        if not hasattr(mod, "resume"):
            raise RuntimeError(f"Flow {run_doc['flow']} lacks a resume(state,next_node) helper")

        # Invoke the flow from the saved node
        mod.resume(state, next_node)

        runs.update_one({"_id": run_doc["_id"]},
                        {"$set": {"status": "done", "updated": datetime.utcnow()}})
    except Exception as exc:
        traceback.print_exc()
        runs.update_one({"_id": run_doc["_id"]},
                        {"$set": {"status": "error", "error": str(exc)}})


# --- small helpers -----------------------------------------------
def _ok(req, payload):
    body = json.dumps(payload).encode()
    req.send_response(200)
    req.send_header("Content-Type", "application/json")
    req.send_header("Content-Length", str(len(body)))
    req.end_headers()
    req.wfile.write(body)


def _error(req, code, payload):
    body = json.dumps(payload).encode()
    req.send_response(code)
    req.send_header("Content-Type", "application/json")
    req.send_header("Content-Length", str(len(body)))
    req.end_headers()
    req.wfile.write(body)

