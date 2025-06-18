#!/usr/bin/env python3
import argparse
import os
import requests
import urllib3
import json
from urllib.parse import quote

# disable warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE           = "https://localhost:8000"
DEFAULT_TENANT = "ethz"
DEFAULT_COLL   = "test_collection"
DEFAULT_PATH   = "test_dir/paper.pdf"

def pretty_print(obj):
    print(json.dumps(obj, indent=2))

def list_tenants():
    print("==> GET /files")
    resp = requests.get(f"{BASE}/files", verify=False)
    resp.raise_for_status()
    pretty_print(resp.json())

def list_collections(tenant):
    print(f"\n==> GET /files/{tenant}")
    resp = requests.get(f"{BASE}/files/{tenant}", verify=False)
    resp.raise_for_status()
    pretty_print(resp.json())

def list_files(tenant, collection):
    print(f"\n==> GET /files/{tenant}/{collection}")
    resp = requests.get(f"{BASE}/files/{tenant}/{collection}", verify=False)
    resp.raise_for_status()
    pretty_print(resp.json())

def fetch_file(tenant, collection, remote_path):
    encoded = quote(remote_path, safe="/")
    url = f"{BASE}/files/{tenant}/{collection}/{encoded}"
    print(f"\n==> GET {url}")
    resp = requests.get(url, verify=False, stream=True)
    if resp.status_code != 200:
        print("Error:", resp.status_code, resp.text)
        return
    ct  = resp.headers.get("Content-Type")
    ln  = resp.headers.get("Content-Length", "unknown")
    print(f"Content-Type: {ct}, Content-Length: {ln}")
    outname = os.path.basename(remote_path)
    with open(outname, "wb") as f:
        for chunk in resp.iter_content(4096):
            f.write(chunk)
    print(f"Saved file to ./{outname}")

def main():
    parser = argparse.ArgumentParser(
        description="List tenants/collections/files and download a nested file"
    )
    parser.add_argument("-t","--tenant",   default=DEFAULT_TENANT,
                        help="Tenant code (default: ethz)")
    parser.add_argument("-c","--collection", default=DEFAULT_COLL,
                        help="Collection name under tenant")
    parser.add_argument("-p","--path",     default=DEFAULT_PATH,
                        help="Remote file path under the collection (e.g. 'dir/sub/file.ext')")
    args = parser.parse_args()

    list_tenants()
    list_collections(args.tenant)
    list_files(args.tenant, args.collection)
    fetch_file(args.tenant, args.collection, args.path)

if __name__ == "__main__":
    main()

