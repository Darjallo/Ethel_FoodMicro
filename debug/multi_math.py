#!/usr/bin/env python3
"""
Async CLI client for Ethelflow /flow that submits a math expression and prints results.

Example:
  python flow_eval.py "4*42"
  python flow_eval.py "integrate(sin(x), x)" --flow multi_math_check --tenant ethz
  python flow_eval.py "4*42" --json

Requires:
  pip install httpx
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


@dataclass
class RunResult:
    ok: bool
    status_code: int
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


def _safe_json_dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True)


def _extract_executor_summary(payload: Dict[str, Any]) -> str:
    """
    Best-effort summary from a typical multi_math_check response.
    """
    expr = payload.get("expression", "")
    maxima = payload.get("maxima_results") or {}
    py = payload.get("python_results") or {}

    maxima_rc = maxima.get("return_code")
    maxima_out = (maxima.get("stdout") or "").strip()
    maxima_err = (maxima.get("stderr") or "").strip()

    py_rc = py.get("return_code")
    py_out = (py.get("stdout") or "").strip()
    py_err = (py.get("stderr") or "").strip()

    reasoning = payload.get("reasoning_result")

    lines = []
    lines.append(f"Expression: {expr}")

    if maxima_rc is not None:
        lines.append(f"\nMaxima return_code: {maxima_rc}")
        if maxima_out:
            lines.append("Maxima stdout:")
            lines.append(maxima_out)
        if maxima_err and maxima_err != maxima_out:
            lines.append("Maxima stderr:")
            lines.append(maxima_err)

    if py_rc is not None:
        lines.append(f"\nPython return_code: {py_rc}")
        if py_out:
            lines.append("Python stdout:")
            lines.append(py_out)
        if py_err and py_err != py_out:
            lines.append("Python stderr:")
            lines.append(py_err)

    if reasoning is not None:
        lines.append("\nReasoning:")
        lines.append(str(reasoning).strip())

    return "\n".join(lines).strip() + "\n"


async def call_flow(
    *,
    url: str,
    flow: str,
    tenant: str,
    expression: str,
    stream: bool,
    timeout_s: float,
) -> RunResult:
    payload = {
        "flow": flow,
        "tenant": tenant,
        "context": {"expression": expression},
        "stream": stream,
    }

    timeout = httpx.Timeout(timeout_s, connect=min(10.0, timeout_s))
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, json=payload)
        except httpx.ConnectError as e:
            return RunResult(
                ok=False,
                status_code=0,
                error=f"Connection error: {e}",
            )
        except httpx.ReadTimeout:
            return RunResult(
                ok=False,
                status_code=0,
                error=f"Request timed out after {timeout_s:.1f}s",
            )
        except httpx.HTTPError as e:
            return RunResult(
                ok=False,
                status_code=0,
                error=f"HTTP error: {e}",
            )

    status = resp.status_code

    # Handle non-2xx with best-effort body extraction
    if status < 200 or status >= 300:
        body_preview = resp.text.strip()
        if len(body_preview) > 2000:
            body_preview = body_preview[:2000] + "…"
        return RunResult(
            ok=False,
            status_code=status,
            error=f"Server returned HTTP {status}\n{body_preview}",
        )

    # Parse JSON
    try:
        data = resp.json()
    except ValueError as e:
        body_preview = resp.text.strip()
        if len(body_preview) > 2000:
            body_preview = body_preview[:2000] + "…"
        return RunResult(
            ok=False,
            status_code=status,
            error=f"Response was not valid JSON: {e}\n{body_preview}",
        )

    return RunResult(ok=True, status_code=status, data=data)


def _decide_exit_code(payload: Dict[str, Any]) -> int:
    """
    Nonzero exit if either executor return_code is nonzero (when present).
    """
    maxima = payload.get("maxima_results") or {}
    py = payload.get("python_results") or {}
    rcs = []
    if "return_code" in maxima:
        rcs.append(maxima.get("return_code"))
    if "return_code" in py:
        rcs.append(py.get("return_code"))
    # If return codes are present and any is nonzero -> failure
    if rcs and any((rc is None) or (int(rc) != 0) for rc in rcs):
        return 2
    return 0


async def main_async(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Submit an expression to Ethelflow /flow and print results."
    )
    p.add_argument("expression", help="Expression to evaluate (e.g., '4*42')")
    p.add_argument(
        "--url",
        default="http://localhost:8080/flow",
        help="Flow endpoint URL (default: http://localhost:8080/flow)",
    )
    p.add_argument(
        "--flow",
        default="multi_math_check",
        help="Flow name (default: multi_math_check)",
    )
    p.add_argument(
        "--tenant",
        default="ethz",
        help="Tenant (default: ethz)",
    )
    p.add_argument(
        "--stream",
        action="store_true",
        help="Request streaming (default: false). Note: this client expects JSON response.",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Request timeout in seconds (default: 60)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON response instead of a summary",
    )

    args = p.parse_args(argv)

    res = await call_flow(
        url=args.url,
        flow=args.flow,
        tenant=args.tenant,
        expression=args.expression,
        stream=args.stream,
        timeout_s=args.timeout,
    )

    if not res.ok:
        print(f"ERROR: {res.error}", file=sys.stderr)
        return 1

    assert res.data is not None

    if args.json:
        print(_safe_json_dumps(res.data))
    else:
        print(_extract_executor_summary(res.data), end="")

    return _decide_exit_code(res.data)


def main() -> None:
    try:
        code = asyncio.run(main_async(sys.argv[1:]))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        code = 130
    raise SystemExit(code)


if __name__ == "__main__":
    main()

