# debug/send_test_flow.py
import requests, urllib3, sys, json

# Suppress warnings for self-signed HTTPS certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://localhost:8000/"

# 1) Non-streaming test (unchanged)
print("Non-streaming test:\n-------------------")
payload = {
    "flow": "test_flow",
    "context": {"message": "Hello World"}
}
resp = requests.post(URL, json=payload, timeout=5, verify=False)
resp.raise_for_status()
print("Non-stream response:")
print(json.dumps(resp.json(), indent=2))


# 2) Streaming test
print("\n================\nStreaming test:\n-------------------")
payload = {
    "flow": "test_flow",
    "context": {"message": "Hello World again"},
    "stream": True
}

# Note: we pass `stream=True` and then read from resp.raw
resp = requests.post(URL, json=payload, timeout=60, verify=False, stream=True)
resp.raise_for_status()

print("Streamed output:", end="", flush=True)

buf = b""
# read one byte at a time
while True:
    byte = resp.raw.read(1)
    if not byte:
        # EOF
        break
    buf += byte
    if byte == b"\n":
        # we've got a full JSON line
        line = buf.decode("utf-8")
        buf = b""
        try:
            packet = json.loads(line)
        except json.JSONDecodeError:
            # definitely not JSON? just print raw
            sys.stdout.write(line)
            sys.stdout.flush()
            continue

        # This is the wrapper your flow_manager emits:
        #   {"test_agent": {"test_agent_result": {"output": "X", ... }}}
        # Or, if you rename the node, adjust accordingly.
        node_key = next(iter(packet))              # e.g. "test_agent"
        payload = packet[node_key]["test_agent_result"]
        ch = payload.get("output", "")
        # print that single character:
        sys.stdout.write(ch)
        sys.stdout.flush()

print()  # final newline

