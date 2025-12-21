#!/usr/bin/env python3
"""
Async streaming client for EthelFlow /flow endpoint.

Requires:
  pip install httpx

This is the async equivalent of:
curl -X POST "http://localhost:8080/flow" \
  -H "Content-Type: application/json" \
  -d '{... "stream": true}'
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Dict, Optional

import httpx


FLOW_URL = "http://localhost:8080/flow"


async def stream_flow_response(
    url: str,
    payload: Dict[str, Any],
    timeout_s: float = 300.0,
    *,
    headers: Optional[Dict[str, str]] = None,
) -> None:
    """
    Send request and print streaming response incrementally.

    Handles common streaming formats:
      - plain newline-delimited text
      - SSE where lines start with "data: ..."
    """
    merged_headers = {"Content-Type": "application/json"}
    if headers:
        merged_headers.update(headers)

    timeout = httpx.Timeout(timeout_s)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=merged_headers, json=payload) as resp:
            resp.raise_for_status()

            async for line in resp.aiter_lines():
                if not line:
                    continue

                # SSE-style "data: ..." lines
                if line.startswith("data:"):
                    line = line[len("data:") :].lstrip()

                print(line, flush=True)


async def amain() -> int:
    payload: Dict[str, Any] = {
        "flow": "reasoning_multiprompt",
        "tenant": "ethz",
        "context": {
            "prompt_1": "Can you give me 20 mountain peaks over 5000m?",
            "prompt_2": "Now can you list these peaks by their height, in descending order?",
            "reasoning_effort": "low",
            "deployment": "Ethel_o4_mini",
        },
        "stream": True,
    }

    try:
        await stream_flow_response(FLOW_URL, payload)
    except httpx.HTTPStatusError as e:
        # Non-2xx response
        print(f"HTTP error {e.response.status_code}: {e}", file=sys.stderr)
        try:
            print(e.response.text, file=sys.stderr)
        except Exception:
            pass
        return 1
    except httpx.RequestError as e:
        # Network / connection / timeout errors
        print(f"Request failed: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))

