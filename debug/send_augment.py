#!/usr/bin/env python3
import argparse
import json
import sys
import requests
import urllib3
from urllib.parse import urljoin

# Suppress warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Invoke the 'augment' flow with a single query string."
    )
    parser.add_argument("query", help="Text to embed + search (quote if needed)")
    parser.add_argument(
        "-u", "--url",
        default="https://localhost:8000/",
        help="Base Flow-Manager URL (default: https://localhost:8000/)"
    )
    parser.add_argument(
        "-t", "--tenant",
        default="ethz",
        help="Tenant code (default: ethz)"
    )
    parser.add_argument(
        "-c", "--collection",
        default="test_collection",
        help="Collection to search (default: test_collection)"
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Ask Flow-Manager for streaming mode"
    )
    args = parser.parse_args()

    # Ensure trailing slash so urljoin works
    base_url = args.url if args.url.endswith("/") else args.url + "/"

    payload = {
        "tenant": args.tenant,          # ← REQUIRED by flow_manager
        "flow":   "augment",
        "query": {
            "text":       args.query,
            "collection": args.collection,
        },
        "stream":      args.stream,
        "flow_reload": False
    }

    try:
        resp = requests.post(
            base_url,
            json=payload,
            verify=False,      # remove if you have a trusted cert
            timeout=60
        )
        resp.raise_for_status()   # raises for 4xx / 5xx only
    except requests.exceptions.HTTPError as e:
        r = e.response           # always present in this except block
        print(
            f"HTTP {r.status_code} error\nResponse body:\n{r.text}",
            file=sys.stderr
        )
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print("Request failed:", e, file=sys.stderr)
        sys.exit(1)

    # Success: pretty-print JSON or raw text
    try:
        data = resp.json()
        print(json.dumps(data, indent=2))
    except ValueError:
        print(resp.text)


if __name__ == "__main__":
    main()

