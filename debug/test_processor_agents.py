#!/usr/bin/env python3
import json
import requests
import urllib3

# If you’re using self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FLOW_MANAGER_URL = "http://localhost:8000/"  # adjust if needed

def invoke_test_processors():
    payload = {
        "flow":       "test_processors",
        "query":      {},       # no extra query params
        "stream":     False,
        "flow_reload": False    # set True if you’ve updated the flow code
    }
    resp = requests.post(FLOW_MANAGER_URL, json=payload, verify=False, timeout=60)
    resp.raise_for_status()
    return resp.json()

if __name__ == "__main__":
    print("\n--- Invoking test_processors flow ---")
    result = invoke_test_processors()
    print(json.dumps(result, indent=2))
    print("\n--- Done ---")

