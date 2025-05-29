import requests
import urllib3
import json
import time

# disable warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://localhost:8000/"

def non_stream_test():
    print("NON-STREAMING test:")
    payload = {
        "flow":   "test_flow",
        "flow_reload": True,
        "context": {"question": "What is the meaning of life?"},
        "stream": False
    }
    resp = requests.post(URL, json=payload, verify=False, timeout=5)
    resp.raise_for_status()
    print(json.dumps(resp.json(), indent=2))
    print()

def stream_test():
    print("STREAMING test:")
    payload = {
        "flow":   "test_flow",
        "context": {"question": "What is the meaning of life?"},
        "stream": True
    }
    # open a chunked GET
    resp = requests.post(URL, json=payload, stream=True, verify=False, timeout=10)
    resp.raise_for_status()

    # iterate as soon as each line arrives
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        # each line is one JSON update
        try:
            obj = json.loads(line)
            print(f"> {json.dumps(obj)}")
        except json.JSONDecodeError:
            # fallback: raw
            print(f"> [raw chunk] {line}")
    print()

if __name__ == "__main__":
    non_stream_test()
    time.sleep(0.5)
    stream_test()

