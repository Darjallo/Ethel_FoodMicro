#!/usr/bin/env python3
import argparse
import os
import sys
import requests
import urllib3
from urllib.parse import urljoin

# Suppress the InsecureRequestWarning if you're using a self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def main():
    p = argparse.ArgumentParser(
        description="Upload a file to the Flow Manager /upload endpoint, then invoke the 'emb_file' flow"
    )
    p.add_argument("file", help="Local path to the file to upload")
    p.add_argument(
        "--collection", "-c",
        default="test_collection",
        help="Target collection name (defaults to 'test_collection')"
    )
    p.add_argument(
        "--path", "-p",
        help="Remote file path (defaults to the exact relative path you passed)"
    )
    p.add_argument(
        "--url", "-u",
        default="https://localhost:8000/upload",
        help="Flow Manager upload URL (defaults to 'https://localhost:8000/upload')"
    )
    args = p.parse_args()

    if not os.path.isfile(args.file):
        print(f"Error: file '{args.file}' does not exist or is not a file.", file=sys.stderr)
        sys.exit(1)

    # Determine the remote_path (preserve relative path unless overridden)
    if args.path:
        remote_path = args.path
    else:
        remote_path = os.path.normpath(args.file)
        if remote_path.startswith(f".{os.sep}"):
            remote_path = remote_path[2:]

    # 1) Upload the file to /upload
    with open(args.file, "rb") as f:
        files = {
            "file": (os.path.basename(args.file), f)
        }
        data = {
            "collection": args.collection,
            "path":      remote_path
        }
        print(f"Uploading '{args.file}' → collection='{args.collection}', path='{remote_path}' …")
        try:
            resp = requests.post(
                args.url,
                files=files,
                data=data,
                verify=False,
                timeout=60
            )
            resp.raise_for_status()
        except Exception as e:
            print("Upload failed:", e, file=sys.stderr)
            sys.exit(1)

    try:
        upload_result = resp.json()
        print("Upload response:", upload_result)
    except ValueError:
        print("Upload non-JSON response:", resp.text)
        sys.exit(1)

    # 2) Invoke the 'emb_file' flow
    # Determine the base Flow Manager URL (remove "/upload" suffix if present)
    if args.url.endswith("/upload"):
        base_url = args.url[: -len("/upload")]
    else:
        # If the URL doesn’t literally end with "/upload", strip off path after the host
        # e.g. "https://host:8000/upload" → "https://host:8000"
        #       "https://host:8000/api/upload" → "https://host:8000/api"
        base_url = args.url.rsplit("/", 1)[0]

    flow_url = urljoin(base_url + "/", "")  # ensures trailing slash
    print(f"Invoking 'emb_file' flow at {flow_url} …")

    flow_payload = {
        "flow": "emb_file",
        "query": {
            "file_id": f"{args.collection}/{remote_path}"
        },
        "stream": False,
        "flow_reload": False
    }

    try:
        flow_resp = requests.post(
            flow_url,
            json=flow_payload,
            verify=False,
            timeout=120
        )
        flow_resp.raise_for_status()
    except Exception as e:
        print("Flow invocation failed:", e, file=sys.stderr)
        sys.exit(1)

    try:
        flow_result = flow_resp.json()
        print("Flow response:", flow_result)
    except ValueError:
        print("Flow non-JSON response:", flow_resp.text)
        sys.exit(1)


if __name__ == "__main__":
    main()

