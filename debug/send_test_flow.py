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

full_text = ""
for line in resp.iter_lines(decode_unicode=True):
    if line:
        try:
            obj = json.loads(line)
            print(f"[Control Message]: {json.dumps(obj, indent=2)}")
            # Handle control messages or content appropriately here
            if "livestream_control" in obj:
                livestream_target = obj["livestream_control"].get("livestream")
                print(f"[Livestream control]: {livestream_target}")
            elif "test_agent" in obj:
                result = obj["test_agent"]["test_agent_result"]
                full_text += result
                print(result, end="", flush=True)
        except json.JSONDecodeError:
            # This shouldn't occur with line-delimited JSON
            print(f"[Malformed JSON]: {line}")

print("\n\nFull streamed message:", full_text.strip())

