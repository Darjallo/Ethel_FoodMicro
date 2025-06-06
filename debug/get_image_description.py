#!/usr/bin/env python3
import argparse
import json
import os
import sys
import requests
import urllib3
from urllib.parse import urljoin

# Suppress the InsecureRequestWarning if using self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def invoke_flow(base_url: str, prompt: str, file_id: str, stream: bool):
    """
    Helper to POST to / with flow="reasoning_test", capturing either a one-shot JSON or streaming JSON lines.
    """
    payload = {
        "flow": "reasoning_test",
        "query": {
            "prompt": prompt,
            "file_id": file_id
        },
        "stream": stream,
        "flow_reload": False  # set True if you want to pick up code changes
    }

    try:
        resp = requests.post(base_url, json=payload, verify=False, timeout=300, stream=stream)
        resp.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Flow invocation failed: {e}", file=sys.stderr)
        sys.exit(1)

    if stream:
        print("\n--- Streaming response ---")
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                # skip any non-JSON lines
                continue
            print(json.dumps(obj, indent=2))
        print("\n--- End of stream ---\n")
    else:
        print("\n--- Non-streaming response ---")
        try:
            obj = resp.json()
        except ValueError:
            print("Non-JSON response:", resp.text)
            return
        print(json.dumps(obj, indent=2))
        print("\n--- End of non-streaming response ---\n")


def main():
    parser = argparse.ArgumentParser(
        description="Invoke reasoning_test flow against a test image in MongoDB"
    )
    parser.add_argument(
        "--url", "-u",
        default="https://localhost:8000/",
        help="Base Flow Manager URL (e.g. https://localhost:8000/ )"
    )
    parser.add_argument(
        "--file_id", "-f",
        default="test_collection/test_dir/timeres.gif",
        help="The file_id already stored in GridFS to send to the reasoning model"
    )
    parser.add_argument(
        "--prompt", "-p",
        default="Describe the attached graph",
        help="Prompt to send to the reasoning model"
    )
    args = parser.parse_args()

    # Ensure the base URL ends with a slash
    base_url = args.url
    if not base_url.endswith("/"):
        base_url += "/"

    # 1) Non-streaming invocation
    invoke_flow(base_url, args.prompt, args.file_id, stream=False)

    # 2) Streaming invocation
    invoke_flow(base_url, args.prompt, args.file_id, stream=True)


if __name__ == "__main__":
    main()

