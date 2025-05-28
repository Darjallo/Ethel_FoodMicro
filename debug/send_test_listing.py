#!/usr/bin/env python3
import requests
import urllib3
import json
import os
from urllib.parse import quote

# disable warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://localhost:8000"
COLLECTION = "test_collection"
FILENAME   = "paper.pdf"

def pretty_print(obj):
    print(json.dumps(obj, indent=2))

def list_root():
    print("==> GET /files")
    resp = requests.get(f"{BASE}/files", verify=False)
    resp.raise_for_status()
    pretty_print(resp.json())

def list_collection():
    print(f"\n==> GET /files/{COLLECTION}")
    resp = requests.get(f"{BASE}/files/{COLLECTION}", verify=False)
    resp.raise_for_status()
    pretty_print(resp.json())

def fetch_file():
    # URL-encode the filename just in case
    path = quote(FILENAME, safe="/")
    url = f"{BASE}/files/{COLLECTION}/{path}"
    print(f"\n==> GET {url}")
    resp = requests.get(url, verify=False, stream=True)
    if resp.status_code != 200:
        print("Error:", resp.status_code, resp.text)
        return

    content_type = resp.headers.get("Content-Type")
    size = resp.headers.get("Content-Length", "unknown")
    print(f"Content-Type: {content_type}, Content-Length: {size}")

    # save to disk
    outpath = f"downloaded_{FILENAME}"
    with open(outpath, "wb") as f:
        for chunk in resp.iter_content(4096):
            f.write(chunk)
    print(f"Saved file to ./{outpath}")

if __name__ == "__main__":
    list_root()
    list_collection()
    fetch_file()

