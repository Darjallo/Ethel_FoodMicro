#!/usr/bin/env python3
import argparse
import os
import sys
import requests
import urllib3
import json
from urllib.parse import urljoin

# Suppress the InsecureRequestWarning if you're using a self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TENANT = "ethz"

def main():
    p = argparse.ArgumentParser(
        description="Upload a file (tenant='ethz') to the Flow Manager /upload endpoint, then invoke the 'emb_file' flow (streaming)."
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
        default="https://localhost/assets/upload",
        help="Flow Manager upload URL (defaults to 'https://localhost/assets/upload')"
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
            "tenant":     TENANT,
            "collection": args.collection,
            "path":       remote_path
        }
        print(f"Uploading '{args.file}' → tenant='{TENANT}', collection='{args.collection}', path='{remote_path}' …")
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
        print("Upload response:", json.dumps(upload_result, indent=2))
    except ValueError:
        print("Upload non-JSON response:", resp.text)
        sys.exit(1)

    # 2) Invoke the 'emb_file' flow (streaming)
    base_url = "https://localhost:8000"

    flow_url = urljoin(base_url + "/", "")  # ensures trailing slash
    # Prefix tenant to file_id
    file_id = f"{TENANT}/{args.collection}/{remote_path}"

    print(f"\nInvoking 'emb_file' flow at {flow_url} with file_id='{file_id}' …\n")

    flow_payload = {
        "tenant":     TENANT,
        "flow":       "emb_file",
        "file_id":    file_id,
        "stream":     True,
        "flow_reload": True
    }

    try:
        # Note: stream=True so we can iterate over lines as they arrive
        flow_resp = requests.post(
            flow_url,
            json=flow_payload,
            verify=False,
            timeout=600,
            stream=True
        )
        flow_resp.raise_for_status()
    except Exception as e:
        print("Flow invocation failed:", e, file=sys.stderr)
        sys.exit(1)

    # 3) Read and print each intermediate update
    print("Streaming updates from the flow (one JSON object per line):\n")
    update_count = 0
    for line in flow_resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        update_count += 1
        try:
            parsed = json.loads(line)
            print(f"=== Update #{update_count} ===")
            print(json.dumps(parsed, indent=2))
            print()
        except ValueError:
            # If a line is not valid JSON, just print it raw
            print(f"=== Update #{update_count} (non-JSON) ===")
            print(line)
            print()

    # 4) After streaming finishes, report total updates
    print(f"Stream ended after {update_count} update(s).")

if __name__ == "__main__":
    main()


