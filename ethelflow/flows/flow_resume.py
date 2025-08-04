# Project Ethel
# Persistence helpers for the pause / resume mechanism
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
# flow_resume.py
#
"""

* save_run(...)        -> called by Flow Manager when a node yields {"pause": True}
* mark_task_done(...)  -> called by async_agent_handler when the human / async agent
                          posts results back to /async_agent
"""

import os
from datetime import datetime
from typing import Dict, Any
from pymongo import MongoClient, ReturnDocument
from ethelflow.settings.mongodb_settings import settings as mongodb_settings

# --------------------------------------------------------------------
# Mongo connection
# --------------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017")
MONGO_DB = os.getenv("MONGO_DB", "ethel_files")

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

runs = db.flow_runs  # stores frozen flow state
tasks = db.human_tasks  # optional: track human-task docs (upsert only)

# Ensure an index for quick look-ups
runs.create_index("status")
tasks.create_index("status")


# --------------------------------------------------------------------
# Save a paused run
# --------------------------------------------------------------------
def save_run(
    run_id: str, flow_name: str, state: Dict[str, Any], next_node: str
) -> None:
    """
    Persist (or overwrite) a paused flow run.  'state' must be plain
    JSON-serialisable dict (no custom objects).  next_node is the
    name of the node the flow should start with upon resume.
    """
    runs.replace_one(
        {"_id": run_id},
        {
            "_id": run_id,
            "flow": flow_name,
            "state": state,
            "next_node": next_node,
            "status": "waiting_async",
            "created": datetime.utcnow(),
            "updated": datetime.utcnow(),
        },
        upsert=True,
    )


# --------------------------------------------------------------------
# Mark async task done & flip run to "resumed"
# --------------------------------------------------------------------
def mark_task_done(task_id: str, run_id: str, result: Dict[str, Any]) -> None:
    """
    * Store the async/human result (optional: in human_tasks collection)
    * Flip the associated run's status to 'resumed'
      (Flow Manager will immediately resume it in a background thread)
    """
    if task_id:
        tasks.update_one(
            {"_id": task_id},
            {
                "$set": {
                    "status": "done",
                    "result": result,
                    "completed": datetime.utcnow(),
                }
            },
            upsert=True,
        )

    runs.update_one(
        {"_id": run_id},
        {
            "$set": {
                "status": "resumed",
                "async_result": result,
                "updated": datetime.utcnow(),
            }
        },
    )


# --------------------------------------------------------------------
# Optional helpers (could be used for admin/debug tooling)
# --------------------------------------------------------------------
def get_run(run_id: str) -> Dict[str, Any] | None:
    """Return the run document, or None if not found."""
    return runs.find_one({"_id": run_id})


def list_waiting() -> list[Dict[str, Any]]:
    """Return all runs waiting for async completion."""
    return list(runs.find({"status": "waiting_async"}))
