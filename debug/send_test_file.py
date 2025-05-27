#!/usr/bin/env python3
import argparse
import os
import sys
import requests
import urllib3

# Suppress the InsecureRequestWarning if you're using a self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def main():
    p = argparse.ArgumentParser(
        description="Upload a file to the Flow Manager /upload endpoint"
    )
    p.add_argument("file", help="Local path to the file to upload")
    p.add_argument(
        "--collection", "-c",
        default="test_collection",
        help="Target collection name (defaults to 'test_collection')"
    )
    p.add_argument(
        "--path", "-p",
        help="Remote file path (defaults to basename of the file)"
    )
    p.add_argument(
        "--url", "-u",
        default="https://localhost:8000/upload",
        help="Flow Manager upload URL"
    )
    args = p.parse_args()

    if not os.path.isfile(args.file):
        print(f"Error: file '{args.file}' does not exist or is not a file.", file=sys.stderr)
        sys.exit(1)

    remote_path = args.path or os.path.basename(args.file)

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
        print("Response:", resp.json())
    except ValueError:
        print("Non-JSON response:", resp.text)

if __name__ == "__main__":
    main()

