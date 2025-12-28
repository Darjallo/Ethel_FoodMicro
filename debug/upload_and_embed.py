#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from typing import Any, Dict, Optional

import httpx


DEFAULT_BASE_URL = "http://localhost:8080"


def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def default_title(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def upload_document(client: httpx.Client, file_path: str, title: str) -> Dict[str, Any]:
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "application/octet-stream")}
        r = client.post("/docs", params={"title": title}, files=files, timeout=120.0)

    if r.status_code >= 300:
        # give a helpful hint for the specific failure you hit
        if r.status_code == 500 and "relation \"etheldocuments\" does not exist" in r.text:
            raise RuntimeError(
                "Upload failed because Postgres tables are missing.\n"
                "Run the init script to create tables (SQLModel.metadata.create_all) "
                "or run your Alembic migrations.\n\n"
                f"Server said: {r.text}"
            )
        raise RuntimeError(f"Upload failed HTTP {r.status_code}: {r.text}")

    doc = r.json()
    if "id" not in doc:
        raise RuntimeError(f"Upload response missing 'id': {doc}")
    return doc


def run_flow_sync(
    client: httpx.Client,
    flow: str,
    context: Dict[str, Any],
    tenant: str = "debug",
) -> Any:
    body = {
        "flow": flow,
        "tenant": tenant,
        "context": context,
        "stream": False,
    }
    r = client.post("/flow", json=body, timeout=600.0)  # embedding + chunking can take time
    if r.status_code >= 300:
        raise RuntimeError(f"POST /flow failed HTTP {r.status_code}: {r.text}")
    try:
        return r.json()
    except Exception:
        return r.text


def start_flow_async(
    client: httpx.Client,
    flow: str,
    context: Dict[str, Any],
    tenant: str = "debug",
) -> str:
    body = {
        "flow": flow,
        "tenant": tenant,
        "context": context,
        "stream": False,
    }
    r = client.post("/flow/start", json=body, timeout=60.0)
    if r.status_code >= 300:
        raise RuntimeError(f"POST /flow/start failed HTTP {r.status_code}: {r.text}")
    data = r.json()
    run_id = data.get("run_id")
    if not run_id:
        raise RuntimeError(f"No run_id in response: {data}")
    return str(run_id)


def poll_status(client: httpx.Client, run_id: str, timeout_s: float = 300.0, poll_s: float = 2.0) -> Any:
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout_s:
        r = client.get(f"/flow/{run_id}/status", timeout=20.0)
        if r.status_code < 300:
            try:
                last = r.json()
            except Exception:
                last = r.text
            print("\n--- status ---")
            print(json.dumps(last, indent=2) if isinstance(last, (dict, list)) else str(last))
        time.sleep(poll_s)
    return last


def main() -> None:
    ap = argparse.ArgumentParser(description="Upload a file to EthelFlow and run e2e_embedding.")
    ap.add_argument("file", help="Path to file (e.g. ./foo/bar.pdf)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"EthelFlow base URL (default: {DEFAULT_BASE_URL})")
    ap.add_argument("--title", default=None, help="Document title (default: filename stem)")
    ap.add_argument("--method", default="recursive_char_1000_100_htmlstrip", help="Chunking method label")
    ap.add_argument("--flow", default="e2e_embedding", help="Flow module name under ethelflow.flows (default: e2e_embedding)")
    ap.add_argument("--tenant", default="debug", help="Tenant string to send in FlowRequest (default: debug)")
    ap.add_argument("--async-flow", action="store_true", help="Use /flow/start + /flow/{run_id}/status instead of /flow")
    ap.add_argument("--insecure", action="store_true", help="Disable TLS verify (only for self-signed https)")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        die(f"Not a file: {args.file}")

    title = args.title or default_title(args.file)

    with httpx.Client(base_url=args.base_url.rstrip("/"), verify=not args.insecure) as client:
        print(f"Base URL: {args.base_url}")
        print(f"Uploading: {args.file}")

        doc = upload_document(client, args.file, title)
        print("\n--- uploaded document ---")
        print(json.dumps(doc, indent=2))

        doc_id = str(doc["id"])
        try:
            uuid.UUID(doc_id)
        except Exception:
            print(f"WARNING: document id doesn't parse as UUID: {doc_id}")

        # Context expected by e2e_embedding.py: uses context.get("document_id")
        context = {"document_id": doc_id, "method": args.method}

        if args.async_flow:
            print(f"\nStarting async flow '{args.flow}'...")
            run_id = start_flow_async(client, args.flow, context=context, tenant=args.tenant)
            print(f"run_id = {run_id}")
            poll_status(client, run_id)
        else:
            print(f"\nRunning flow '{args.flow}' via POST /flow ...")
            result = run_flow_sync(client, args.flow, context=context, tenant=args.tenant)
            print("\n--- flow result ---")
            print(json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result))


if __name__ == "__main__":
    main()

