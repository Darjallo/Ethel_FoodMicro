import requests
import urllib3
import json

# Suppress warnings for self-signed HTTPS certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://localhost:8000/"

print("Non-streaming test:\n-------------------")
payload = {
    "flow": "test_flow",
    "context": {"message": "Hello World"}
}

resp = requests.post(URL, json=payload, timeout=5, verify=False)
resp.raise_for_status()
print("Non-stream response from flow_manager:")
print(json.dumps(resp.json(), indent=2))

print("\n================\nStreaming test:\n-------------------")
payload = {
    "flow": "test_flow",
    "context": {"message": "Hello World again"},
    "stream": True
}

resp = requests.post(URL, json=payload, timeout=60, verify=False, stream=True)
resp.raise_for_status()
print("Stream response from flow_manager:")

for line in resp.iter_lines(decode_unicode=True):
    if not line:
        continue
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        # shouldn't happen with JSON-delimited chunks
        print(f"[Malformed JSON]: {line}")
        continue

    # the streaming node now always lives under the flow's node name
    node_payload = obj.get("test_agent", {}).get("test_agent_result", {})

    # if it's a single character delta
    if "delta" in node_payload:
        print(node_payload["delta"], end="", flush=True)

    # final, full output + metadata
    elif "output" in node_payload and "result" in node_payload:
        print("\n\n[Final output]:", node_payload["output"])
        print("[Full metadata]:", json.dumps(node_payload["result"], indent=2))

print()  # newline at end

