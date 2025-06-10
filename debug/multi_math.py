#!/usr/bin/env python3
"""
test_multi_math.py
==================
Tiny helper to call the `multi_math_check` flow and print either the
one-shot JSON or the streamed chunks.

Usage:
  • Non-streaming (default) : ./test_multi_math.py
  • Streaming               : ./test_multi_math.py --stream
  • Custom expression       : ./test_multi_math.py -e "sin(0)+cos(0)"
"""

import argparse, json, requests, urllib3, sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FLOW_MANAGER_URL = "https://localhost:8000/"


# ----------------------------------------------------------------------
def call_flow(expression: str, stream: bool, reload_code: bool = False):
    payload = {
        "flow":        "multi_math_check",
        "query":       {"expression": expression},
        "stream":      stream,
        "flow_reload": reload_code,
    }
    resp = requests.post(
        FLOW_MANAGER_URL,
        json=payload,
        verify=False,     # allow self-signed certs
        timeout=300,
        stream=stream
    )
    resp.raise_for_status()
    return resp


# ----------------------------------------------------------------------
def pretty_stream(resp):
    print("\n--- Streaming response ---")
    try:
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                obj = json.loads(line)
                print(json.dumps(obj, indent=2))
            except json.JSONDecodeError:
                # Non-JSON chunk (shouldn’t happen, but guard anyway)
                print(line)
    finally:
        print("--- End of stream ---\n")


def pretty_one_shot(resp):
    print("\n--- Non-streaming response ---")
    print(json.dumps(resp.json(), indent=2))
    print("--- End ---\n")


# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Invoke multi_math_check flow")
    ap.add_argument("-e", "--expression", default="6*7+4",
                    help="Math expression to evaluate")
    ap.add_argument("-s", "--stream", action="store_true",
                    help="Stream reasoning agent output")
    ap.add_argument("--reload", action="store_true",
                    help="Set flow_reload=true (useful during dev)")
    args = ap.parse_args()

    try:
        resp = call_flow(args.expression, args.stream, args.reload)
        if args.stream:
            pretty_stream(resp)
        else:
            pretty_one_shot(resp)
    except requests.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        if exc.response is not None:
            print(exc.response.text, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

