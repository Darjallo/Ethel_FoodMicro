#!/usr/bin/env python3
import argparse, json, requests, urllib3, time
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://localhost:8000/"

def start_flow(topic):
    r = requests.post(BASE, json={
        "flow": "human_quiz",
        "query": {"topic": topic},
        "stream": False,
        "flow_reload": True
    }, verify=False)
    r.raise_for_status()
    pause_blob = r.json()["pause_step"]
    return pause_blob["run_id"], pause_blob["question"]

def post_answer(run_id, answer):
    r = requests.post(BASE+"async_agent", json={
        "run_id": run_id,
        "result": {"answer": answer}
    }, verify=False)
    r.raise_for_status()

def poll_result(run_id):
    while True:
        r = requests.get(BASE+f"run/{run_id}", verify=False)
        if r.status_code == 200:
            data = r.json()
            if data["status"] == "done":
                return data["feedback"]
        time.sleep(2)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("topic")
    args = ap.parse_args()

    run_id, question = start_flow(args.topic)
    print("\nQuestion:", question)
    ans = input("Your answer: ").strip()
    post_answer(run_id, ans)
    print("Waiting for feedback ...")
    fb = poll_result(run_id)
    print("\nFeedback:\n", json.dumps(fb, indent=2))

