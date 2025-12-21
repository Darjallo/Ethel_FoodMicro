#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast  # ### CHANGED
import json
import re
import sys
import urllib.error
import urllib.request
from typing import Optional, Tuple, Dict, Any

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

# We expect LangGraph interrupt events to show up as:
# "__interrupt__': (Interrupt(value='...', id='abcdef...'),)}"
INTERRUPT_ID_RE = re.compile(r"id='([0-9a-fA-F]+)'")

# NOTE: keep this, but we will decode the captured value safely
INTERRUPT_VALUE_RE = re.compile(
    r"Interrupt\(value=(?P<lit>'(?:\\.|[^'])*'|\"(?:\\.|[^\"])*\"),\s*id='[0-9a-fA-F]+'\)",
    re.DOTALL,
)  # ### CHANGED (capture the full quoted literal)

THREAD_ID_RE = re.compile(r"thread_id': '(" + UUID_RE.pattern + r")'")
RUN_ID_RE = re.compile(r"run_id': '(" + UUID_RE.pattern + r")'")

# For feedback, DO NOT trigger on "Correct Answer:" early; it can appear in prompt templates.
# We'll prefer extracting the actual 'feedback': '...' field.  ### CHANGED
FEEDBACK_FIELD_RE = re.compile(
    r"(?:'feedback'\s*:\s*|\"feedback\"\s*:\s*)(?P<lit>'(?:\\.|[^'])*'|\"(?:\\.|[^\"])*\")",
    re.DOTALL,
)  # ### CHANGED


def _http_json(url: str, payload: Dict[str, Any], timeout_s: int = 60) -> Tuple[int, Dict[str, Any], bytes]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
            ct = resp.headers.get("Content-Type", "")
            if "application/json" in ct:
                try:
                    return resp.status, json.loads(raw.decode("utf-8")), raw
                except Exception:
                    return resp.status, {}, raw
            return resp.status, {}, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, {}, raw


def _http_get_json(url: str, timeout_s: int = 30) -> Tuple[int, Dict[str, Any]]:
    req = urllib.request.Request(url=url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            raw = e.read()
            return e.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return e.code, {}
    except Exception:
        return 0, {}


def _print_block(text: str) -> None:
    line = "=" * 72
    print("\n" + line)
    print(text.rstrip())
    print(line + "\n")
    sys.stdout.flush()


def _decode_python_string_literal(lit: str) -> str:
    """
    Decode a Python string literal INCLUDING its quotes, e.g. "'hi\\n'" or "\"hi\\n\"".
    This safely handles \\n etc and preserves UTF-8 characters like ×.  ### CHANGED
    """
    try:
        return ast.literal_eval(lit)
    except Exception:
        # If it isn't a valid literal for some reason, return raw without quotes as fallback
        if len(lit) >= 2 and lit[0] == lit[-1] and lit[0] in ("'", '"'):
            return lit[1:-1]
        return lit


def _discover_paths(base_url: str) -> Optional[list[str]]:
    code, spec = _http_get_json(base_url.rstrip("/") + "/openapi.json")
    if code != 200 or "paths" not in spec:
        return None
    return sorted(spec["paths"].keys())


def _stream_post(url: str, payload: Dict[str, Any], timeout_s: int = 300):
    """
    Yields decoded text chunks from a streaming HTTP response.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            yield chunk.decode("utf-8", errors="replace")


def _extract_run_id(buf: str) -> Optional[str]:
    m = THREAD_ID_RE.search(buf)
    if m:
        return m.group(1)
    m = RUN_ID_RE.search(buf)
    if m:
        return m.group(1)
    # fallback: any UUID at all (less safe)
    m = UUID_RE.search(buf)
    return m.group(0) if m else None


def _extract_interrupt(buf: str) -> Tuple[Optional[str], Optional[str]]:
    if "__interrupt__" not in buf and "Interrupt(value" not in buf:
        return None, None

    mid = INTERRUPT_ID_RE.search(buf)
    mval = INTERRUPT_VALUE_RE.search(buf)

    interrupt_id = mid.group(1) if mid else None
    interrupt_value = None
    if mval:
        lit = mval.group("lit")  # quoted python literal
        interrupt_value = _decode_python_string_literal(lit)  # ### CHANGED

    return interrupt_id, interrupt_value


def _extract_feedback(buf: str) -> Optional[str]:
    """
    Prefer extracting the real 'feedback' field. Do NOT early-return on "Correct Answer:".
    The marker can appear in a grading prompt template before the final output arrives.  ### CHANGED
    """
    m = FEEDBACK_FIELD_RE.search(buf)
    if m:
        return _decode_python_string_literal(m.group("lit"))

    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Endpoint-only CLI client for EthelFlow quiz flow.")
    ap.add_argument("topic", help="Quiz topic (e.g., Multiplication)")
    ap.add_argument("--base-url", default="http://localhost:8080", help="EthelFlow base URL")
    ap.add_argument("--tenant", default="ethz", help="Tenant")
    ap.add_argument("--deployment", default="Ethel_o4_mini", help="Deployment hint (may be ignored by flow)")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")

    # 1) Start quiz via POST /flow (streaming)
    start_url = base + "/flow"
    start_payload = {
        "flow": "quiz",
        "tenant": args.tenant,
        "context": {
            "topic": args.topic,
            "deployment": args.deployment,
        },
        "stream": True,
    }

    buf = ""
    run_id: Optional[str] = None
    interrupt_id: Optional[str] = None
    question_text: Optional[str] = None

    try:
        for chunk in _stream_post(start_url, start_payload):
            buf += chunk
            if run_id is None:
                run_id = _extract_run_id(buf)

            iid, qtxt = _extract_interrupt(buf)
            if iid and qtxt:
                interrupt_id = iid
                question_text = qtxt
                break

            # Prevent unbounded memory
            if len(buf) > 2_000_000:
                buf = buf[-1_000_000:]

    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} starting quiz at {start_url}\n{raw}")
        return 2
    except Exception as e:
        print(f"Error starting quiz: {e}")
        return 2

    if not run_id:
        print("ERROR: Could not detect a run_id/thread_id in the stream.")
        return 1
    if not interrupt_id or not question_text:
        print("ERROR: Did not find an interrupt in the stream (no Interrupt(..., id='...') seen).")
        print("Tip: try `curl -s http://localhost:8080/openapi.json | head` to confirm you hit EthelFlow.")
        return 1

    _print_block(question_text)

    # 2) Ask user
    answer = input("Your answer> ").strip()

    # 3) Continue via POST /flow/{run_id}/continue
    continue_url = f"{base}/flow/{run_id}/continue"
    cont_payload = {"data": {interrupt_id: answer}, "stream": True}

    # Before continuing, check OpenAPI quickly and warn if endpoint absent.
    paths = _discover_paths(base)
    if paths is not None and "/flow/{run_id}/continue" not in paths:
        print(
            "\nWARNING: /flow/{run_id}/continue is NOT listed in /openapi.json for this server.\n"
            "That usually means you are NOT talking to the same EthelFlow app/router that the repo describes.\n"
        )
        print("Paths containing '/flow' from OpenAPI:")
        for p in paths:
            if "/flow" in p:
                print(" ", p)
        print()

    # Try continue
    buf2 = ""
    try:
        for chunk in _stream_post(continue_url, cont_payload):
            buf2 += chunk
            fb = _extract_feedback(buf2)
            if fb:
                _print_block(fb)
                return 0

            if len(buf2) > 2_000_000:
                buf2 = buf2[-1_000_000:]

        # If stream ends without feedback, check once more.
        fb = _extract_feedback(buf2)
        if fb:
            _print_block(fb)
            return 0

        # Fallback: if there's no feedback field, dump a tail for debugging (non-hanging, small).
        print("Resumed, but did not detect a 'feedback' field in the streamed output.")
        print("\n--- tail of response ---\n" + buf2[-2000:])
        return 0

    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} on continue URL: {continue_url}\n{raw}\n")

        if e.code == 404:
            print(
                "This 404 strongly suggests the service running on this port does not expose\n"
                "POST /flow/{run_id}/continue, even though it exists in the repo and docs.\n"
                "In the repo, the route is defined under an APIRouter(prefix='/flow').\n"
            )
        return 3
    except Exception as e:
        print(f"Error continuing quiz: {e}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

