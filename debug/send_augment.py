#!/usr/bin/env python3
import argparse
import sys
import requests
import urllib3
from urllib.parse import urljoin

# Suppress warnings if using a self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def main():
    p = argparse.ArgumentParser(
        description="Invoke the 'augment' flow with a single query string."
    )
    p.add_argument(
        "query",
        help="The text to embed + search (wrap in quotes if it contains spaces)."
    )
    p.add_argument(
        "--url", "-u",
        default="https://localhost:8000/",
        help="Base Flow Manager URL (default: https://localhost:8000/ )."
    )
    args = p.parse_args()

    payload = {
        "flow": "augment",
        "query": {
            "text": args.query,
            "collection": "test_collection",
            "tenant" : "ethz"
        },
        "stream": False,
        "flow_reload": False
    }

    try:
        resp = requests.post(
            args.url,
            json=payload,
            verify=False,
            timeout=60
        )
        resp.raise_for_status()
    except Exception as e:
        print("Flow invocation failed:", e, file=sys.stderr)
        sys.exit(1)

    try:
        data = resp.json()
        print("Flow response (JSON):")
        print(data)
    except ValueError:
        print("Non-JSON response:")
        print(resp.text)


if __name__ == "__main__":
    main()

