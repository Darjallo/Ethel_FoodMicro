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
import traceback
import base64
from datetime import datetime
from typing import Any, Dict
from agent_pool.base_agent_server import run_server

class ProgrammaticAgent:
    """
    Base class for “script→container” agents.
    Expects these env vars:
      * <LANG>_IMAGE      e.g. MAXIMA_IMAGE="your-maxima-image"
      * <LANG>_CMD        e.g. MAXIMA_CMD="maxima --very-quiet --batch-string"
      * TIMEOUT           per-job timeout in seconds (default 15)
    """
    def __init__(self, lang: str):
        self.lang = lang.upper()
        self.image = os.environ[f"{self.lang}_IMAGE"]
        # command split into list, e.g. ["python", "-I", "-c"]
        self.cmd = os.environ[f"{self.lang}_CMD"].split()
        self.timeout = int(os.getenv("TIMEOUT", "15"))

    def handle(self, request_json: Dict[str, Any]) -> Dict[str, Any]:
        result = {
            "id":      f"{self.lang.lower()}_response",
            "object":  "task_result",
            "created": int(datetime.utcnow().timestamp()),
        }

        script = request_json.get("script")
        if not isinstance(script, str):
            result.update({
                "status": 400,
                "error": "Missing or invalid 'script' field (must be a string)."
            })
            return result

        # Base docker invocation flags
        docker_base = [
            "docker", "run", "--rm",
            "--net=none",                  # no network
            "--read-only",                 # rootfs read-only
            "--tmpfs", "/tmp:rw,size=64m", # only /tmp writable
            "--user", "1000:1000",         # unprivileged user
            "--cap-drop=ALL",              # drop all capabilities
            "--security-opt", "no-new-privileges",
            "--memory=256m",               # resource limits
            "--cpus=0.5",
            self.image
        ]

        try:
            # Determine if script must be passed as CLI argument
            cli_flags = {"-c", "-e", "--batch-string"}
            passes_via_arg = any(flag in self.cmd for flag in cli_flags)

            if passes_via_arg:
                # e.g. python -I -c "print(6*7)"
                full_cmd = docker_base + self.cmd + [script]
                proc = subprocess.run(
                    full_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=self.timeout
                )
            else:
                # fallback: interpreter reads from stdin
                full_cmd = docker_base + self.cmd
                proc = subprocess.run(
                    full_cmd,
                    input=script.encode("utf-8"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=self.timeout
                )

            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")

            result.update({
                "status":  200 if proc.returncode == 0 else 500,
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
        # e.g. MAXIMA_IMAGE and MAXIMA_CMD in env
        super().__init__("MAXIMA")

class RAgent(ProgrammaticAgent):
    def __init__(self):
        super().__init__("R")

class PythonAgent(ProgrammaticAgent):
    def __init__(self):
        super().__init__("PYTHON")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    agent_type = os.getenv("AGENT_TYPE", "MAXIMA").upper()
    if agent_type == "R":
        handler = RAgent()
    elif agent_type == "PYTHON":
        handler = PythonAgent()
    else:
        handler = MaximaAgent()

    run_server(port=port, handler_instance=handler)

