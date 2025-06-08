# Project Ethel
# Agent for running scripts in Python, Maxima, and R
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
import os
import subprocess
import time
import traceback
import base64
from datetime import datetime
from typing import Any, Dict
from agent_pool.base_agent_server import run_server

class ProgrammaticAgent:
    """
    Base class for “script→container” agents.
    Expects these env vars:
      * <LANG>_IMAGE      e.g. MAXIMA_IMAGE="myregistry/maxima-safe:latest"
      * <LANG>_CMD        e.g. MAXIMA_CMD="maxima --batch-string"
      * TIMEOUT           per-job timeout in seconds (default 15)
    """
    def __init__(self, lang: str):
        self.lang = lang.upper()
        self.image = os.environ[f"{self.lang}_IMAGE"]
        self.cmd    = os.environ[f"{self.lang}_CMD"].split()  # list form
        self.timeout = int(os.getenv("TIMEOUT", "15"))

    def handle(self, request_json: Dict[str, Any]) -> Dict[str, Any]:
        result = {
            "id":      f"{self.lang.lower()}_response",
            "object":  "task_result",
            "created": int(datetime.utcnow().timestamp()),
        }

        script = request_json.get("script")
        if not isinstance(script, str):
            result.update({"status": 400,
                           "error": "Missing or invalid 'script' field (must be string)."})
            return result

        try:
            # launch ephemeral container, feed script on stdin
            proc = subprocess.run(
                ["docker", "run", "--rm",
                "--net=none",                    # no network
                "--read-only",                   # make rootfs read-only
                "--tmpfs", "/tmp:rw,size=64m",   # allow only /tmp to be writable
                "--user", "1000:1000",           # run as non-root (match agentuser’s uid/gid)
                "--cap-drop=ALL",                # drop all Linux capabilities
                "--security-opt", "no-new-privileges",
                "--memory=256m",                 # resource limits
                "--cpus=0.5",
                 self.image] + self.cmd,
                input=script.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout
            )

            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")

            # if you expect binary output (e.g. R plots), you could:
            #   img_b64 = base64.b64encode(proc.stdout).decode()
            #   result["image_base64"] = img_b64
            #   and omit capturing stdout as text.

            result.update({
                "status":  proc.returncode == 0 and 200 or 500,
                "stdout":  stdout,
                "stderr":  stderr
            })

        except subprocess.TimeoutExpired:
            result.update({
                "status": 504,
                "error":  f"{self.lang} execution timed out after {self.timeout}s."
            })
        except Exception as exc:
            traceback.print_exc()
            result.update({
                "status": 500,
                "error":  f"Unexpected error: {exc}"
            })

        return result

# --- Specializations ---

class MaximaAgent(ProgrammaticAgent):
    def __init__(self):
        # assumes you set:
        #   MAXIMA_IMAGE="your-maxima-image"
        #   MAXIMA_CMD="maxima --very-quiet --batch-string"
        super().__init__("MAXIMA")

class RAgent(ProgrammaticAgent):
    def __init__(self):
        # assumes:
        #   R_IMAGE="your-r-image"
        #   R_CMD="Rscript -e"
        super().__init__("R")

class PythonAgent(ProgrammaticAgent):
    def __init__(self):
        # assumes:
        #   PYTHON_IMAGE="your-python-image"
        #   PYTHON_CMD="python -I -c"
        super().__init__("PYTHON")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    # register whichever agent you want on this server:
    # e.g. run_server(..., handler_instance=MaximaAgent())
    # or RAgent(), or PythonAgent()
    handler = os.getenv("AGENT_TYPE", "MAXIMA").upper()
    if handler == "R":
        agent = RAgent()
    elif handler == "PYTHON":
        agent = PythonAgent()
    else:
        agent = MaximaAgent()

    run_server(port=port, handler_instance=agent)

