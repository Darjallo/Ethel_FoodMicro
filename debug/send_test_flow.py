import requests
import json
import urllib3
import warnings

# Suppress InsecureRequestWarning for self-signed SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=UserWarning, module='urllib3')

URL = "https://localhost:8000/"  # Adjust if needed

def pretty(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))

# Non-streaming call
payload = {
    "flow": "test_flow",
    "context": {"message": "Hello World"}
}

try:
    resp = requests.post(URL, json=payload, timeout=5, verify=False)
    resp.raise_for_status()
    print("Non-stream response from flow_manager:")
    pretty(resp.json())
except Exception as e:
    print("Error in non-streaming request:", e)
    print("Raw text:", getattr(resp, 'text', ''))

print("\n================\n")

# Streaming call
payload = {
    "flow": "test_flow",
    "context": {"message": "Hello World again"},
    "stream": True
}

try:
    resp = requests.post(URL, json=payload, timeout=10, verify=False, stream=True)
    resp.raise_for_status()
    print("Stream response from flow_manager:")
    for raw in resp.iter_lines():
        if not raw:
            continue
        try:
            # Try to decode the chunk as JSON
            data = json.loads(raw.decode("utf-8"))
            print("Parsed:", end=" ")
            pretty(data)
        except Exception:
            # If not JSON, just print as string for debugging
            print("Raw line (not JSON):", raw.decode("utf-8"))
except Exception as e:
    print("Error in streaming request:", e)
    print("Raw text:", getattr(resp, 'text', ''))

