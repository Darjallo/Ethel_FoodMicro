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
from datetime import datetime
from typing import Any, Dict
from agent_pool.base_agent_server import run_server

class ProgrammaticAgent:
    """
    Base for “script→container” agents.
    Env vars:
      * <LANG>_IMAGE    e.g. MAXIMA_IMAGE="maxima_processor:latest"
      * <LANG>_CMD      e.g. MAXIMA_CMD="maxima --very-quiet --batch-string"
      * TIMEOUT         per-job timeout in seconds (default 15)
    """
    def __init__(self, lang: str):
        self.lang = lang.upper()
        self.image = os.environ[f"{self.lang}_IMAGE"]
        self.cmd   = os.environ[f"{self.lang}_CMD"].split()
        self.timeout = int(os.getenv("TIMEOUT", "15"))

    def handle(self, request_json: Dict[str, Any]) -> Dict[str, Any]:
        result = {
            "id":      f"{self.lang.lower()}_response",
            "object":  "task_result",
            "created": int(datetime.utcnow().timestamp()),
        }

        script = request_json.get("script")
        if not isinstance(script, str):
            return {**result, **{"status": 400, "error": "Missing or invalid 'script'."}}

        # ─── Build docker run args ────────────────────────────────────────────
        common_opts = [
            "docker", "run", "--rm",
            "--net=none",
            "--read-only",
            "--tmpfs", "/tmp:rw,size=64m",
            "--tmpfs", "/home/agentuser:rw,size=64m",
            "--user", "1000:1000",
            "--memory=256m",
            "--cpus=0.5",
        ]

        # drop all caps, plus optionally re-add SYS_ADMIN for Maxima
        cap_opts = ["--cap-drop=ALL", "--security-opt", "no-new-privileges"]
        if self.lang == "MAXIMA":
            cap_opts.insert(1, "--cap-add=SYS_ADMIN")  # after drop
            # …and disable seccomp so personality() can run
            cap_opts += ["--security-opt", "seccomp=unconfined"]

        # Final docker argv prefix:
        docker_args = common_opts + cap_opts + [ self.image ]

        # ─── Build the in-container command ────────────────────────────────────
        if self.lang == "MAXIMA":
            # maxima --very-quiet --batch-string="<script>"
            exe = self.cmd[0]
            other = [c for c in self.cmd[1:] if not c.startswith("--batch-string")]
            batch = next(c for c in self.cmd if c.startswith("--batch-string"))
            in_args = [ exe ] + other + [ f"{batch}={script}" ]
            stdin = None

        else:
            # Python (-c) or Rscript (-e)
            if any(flag in self.cmd for flag in ("-c","-e")):
                in_args = self.cmd + [script]
                stdin = None
            else:
                in_args = self.cmd
                stdin = script.encode("utf-8")

        full_cmd = docker_args + in_args

        # ─── Run and capture ───────────────────────────────────────────────────
        try:
            proc = subprocess.run(
                full_cmd,
                **({"input": stdin} if stdin else {}),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout
            )
            out = proc.stdout.decode("utf-8", errors="replace")
            err = proc.stderr.decode("utf-8", errors="replace")

            if proc.returncode != 0:
                err = err or f"{self.lang} exited with code {proc.returncode}"
                return {**result, **{"status": 500, "error": err, "returncode": proc.returncode}}

            return {**result, **{"status": 200, "stdout": out, "stderr": err}}

        except subprocess.TimeoutExpired:
            return {**result, **{"status": 504, "error": f"{self.lang} timed out after {self.timeout}s"}}
        except Exception as exc:
            traceback.print_exc()
            return {**result, **{"status": 500, "error": f"Unexpected error: {exc}"}}

# --- subclasses ---

class MaximaAgent(ProgrammaticAgent):
    def __init__(self): super().__init__("MAXIMA")

class RAgent(ProgrammaticAgent):
    def __init__(self): super().__init__("R")

class PythonAgent(ProgrammaticAgent):
    def __init__(self): super().__init__("PYTHON")

if __name__ == "__main__":
    port     = int(os.getenv("PORT","8000"))
    typ      = os.getenv("AGENT_TYPE","MAXIMA").upper()
    handler  = {"R":RAgent,"PYTHON":PythonAgent}.get(typ, MaximaAgent)()
    run_server(port=port, handler_instance=handler)

