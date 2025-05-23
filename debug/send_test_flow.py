import requests

URL = "https://localhost:8000/"  # Adjust if your flow_manager is at a different host/port

payload = {
    "flow": "test_flow",
    "context": {"message": "Hello World"}
}

resp = requests.post(URL, json=payload, timeout=5, verify=False)
resp.raise_for_status()
print("Response from flow_manager:")
print(resp.json())

