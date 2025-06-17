#!/usr/bin/env python3
import argparse
import os
import sys
import requests
import urllib3
import json
from urllib.parse import quote

# disable warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE       = "https://localhost:8000"
TENANT     = "ethz"
COLLECTION = "test_collection"
FILENAME   = "paper.pdf"

def pretty_print(obj):
    print(json.dumps(obj, indent=2))

def list_tenants():
    """List all tenants at the top level via GET /files."""
    print("==> GET /files")
    resp = requests.get(f"{BASE}/files", verify=False)
    resp.raise_for_status()
    pretty_print(resp.json())

def list_collections(tenant):
    """List all collections under a specific tenant via GET /files/{tenant}."""
    print(f"\n==> GET /files/{tenant}")
    resp = requests.get(f"{BASE}/files/{tenant}", verify=False)
    resp.raise_for_status()
    pretty_print(resp.json())

def list_files(tenant, collection):
    """List all items under a tenant and collection via GET /files/{tenant}/{collection}."""
    print(f"\n==> GET /files/{tenant}/{collection}")
    resp = requests.get(f"{BASE}/files/{tenant}/{collection}", verify=False)
    resp.raise_for_status()
    pretty_print(resp.json())

def fetch_file(tenant, collection, filename):
    """
    Download a specific file under tenant/collection:
    GET /files/{tenant}/{collection}/{filename}
    """
    path = quote(filename, safe="/")
    url = f"{BASE}/files/{tenant}/{collection}/{path}"
    print(f"\n==> GET {url}")
    resp = requests.get(url, verify=False, stream=True)
    if resp.status_code != 200:
        print("Error:", resp.status_code, resp.text)
        return

    content_type = resp.headers.get("Content-Type")
    size = resp.headers.get("Content-Length", "unknown")
    print(f"Content-Type: {content_type}, Content-Length: {size}")

    outpath = f"downloaded_{filename}"
    with open(outpath, "wb") as f:
        for chunk in resp.iter_content(4096):
            f.write(chunk)
    print(f"Saved file to ./{outpath}")

def main():
    parser = argparse.ArgumentParser(
        description="List tenants, collections, files and optionally download one file"
    )
    parser.add_argument(
        "--tenant", "-t",
        default=TENANT,
        help="Tenant code (default: ethz)"
    )
    parser.add_argument(
        "--collection", "-c",
        default=COLLECTION,
        help="Collection name under the tenant"
    )
    parser.add_argument(
        "--file", "-f",
        default=FILENAME,
        help="Filename to download (optional)"
    )
    args = parser.parse_args()

    list_tenants()
    list_collections(args.tenant)
    list_files(args.tenant, args.collection)
    fetch_file(args.tenant, args.collection, args.file)

if __name__ == "__main__":
    main()

