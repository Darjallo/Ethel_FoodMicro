"""
Minimal stub so async_agent_handler can import mark_task_done
without failing.  Extend later with real DB/persistence logic.
"""

from datetime import datetime
import sys

def mark_task_done(task_id: str, run_id: str, result: dict):
    """
    Placeholder: just log the event to stdout for now.
    Later you’ll:
      1. update human_tasks collection (status=done, result payload)
      2. update flow_runs collection (status=resumed)
    """
    print(
        f"[{datetime.utcnow().isoformat()}] "
        f"mark_task_done(task_id={task_id!r}, run_id={run_id!r}, result={result!r})",
        file=sys.stdout,
        flush=True
    )

