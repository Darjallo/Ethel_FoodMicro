#!/usr/bin/env python3
"""
test_quiz_flow.py
-----------------
1) Starts the `human_quiz` flow with a topic.
2) Gets back the pause payload (inside result["pause_step"]).
3) Prompts you for an answer and POSTs /async_agent.
"""

import argparse, json, requests, urllib3, sys
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://localhost:8000/"

# -------------------------------------------------------------------
def start_flow(topic: str):
    payload = {
        "flow": "human_quiz",
        "query": {"topic": topic},
        "stream": False,
        "flow_reload": True,
    }
    r = requests.post(BASE, json=payload, verify=False, timeout=300)
    r.raise_for_status()
    resp = r.json()

    # flow returns { "pause_step": { ... } }
    pause_blob = resp.get("pause_step")
    if not pause_blob or not pause_blob.get("pause"):
        print("Unexpected response:\n", json.dumps(resp, indent=2))
        sys.exit(1)
    return pause_blob

# -------------------------------------------------------------------
def submit_answer(run_id: str, answer: str):
    payload = {
        "run_id": run_id,
        "result": {"answer": answer}
    }
    r = requests.post(BASE + "async_agent", json=payload, verify=False, timeout=60)
    r.raise_for_status()
    print("✅ answer submitted")

# -------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topic", help="Quiz topic")
    args = ap.parse_args()

    pause_info = start_flow(args.topic)
    print("\nQuiz question:")
    print(pause_info["question"])

    answer = input("\nYour answer: ").strip()
    submit_answer(pause_info["run_id"], answer)

    print("\nNow watch Flow-Manager logs for the feedback.")

if __name__ == "__main__":
    main()

