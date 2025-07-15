# flow_manager/flows/human_quiz.py
from typing import TypedDict, Dict, Any, List, Iterator
from datetime import datetime
import uuid
import os
import copy
from langgraph.graph import StateGraph, START, END
from pymongo import MongoClient

from ethelflow.agents.reasoning_completion.node_adapter import reasoning_completion_node
from ethelflow.flows.flow_helper import extract_query, run_flow
from ethelflow.flows.flow_resume import save_run

# ─────────── Mongo ---------------------------------------------------------------------------------
mongo = MongoClient(os.getenv("MONGO_URI", "mongodb://mongodb:27017"))
db = mongo[os.getenv("MONGO_DB", "ethel_files")]
tasks = db.human_tasks


# ─────────── TypedDict ----------------------------------------------------------------------------
class QuizState(TypedDict, total=False):
    context: dict
    query: Dict[str, Any]
    stream: bool

    topic: str
    messages: List[Dict[str, str]]
    reasoning_result: Dict[str, Any]
    question: str

    # pause payload
    pause: bool
    run_id: str
    task_id: str
    state: Dict[str, Any]
    next_node: str

    # resume
    async_result: Dict[str, Any]
    feedback: Dict[str, Any]


# ─────────── Phase-1  (generate question, pause) ---------------------------------------------------
def run(
    context=None, query=None, file_id=None, stream=False
) -> Iterator[Dict[str, Any]]:
    state: QuizState = {"context": context, "query": query or {}, "stream": stream}
    builder = StateGraph(QuizState)

    builder.add_node("pull", extract_query({"topic": "topic"}))
    builder.add_edge(START, "pull")

    def make_prompt(st):
        t = st["topic"]
        yield {
            "messages": [
                {
                    "role": "user",
                    "content": f"Make up ONE trivia quiz question about {t}. Only output the question.",
                }
            ]
        }

    builder.add_node("prompt", make_prompt)
    builder.add_edge("pull", "prompt")

    builder.add_node(
        "ask",
        reasoning_completion_node(
            input_key_map={"messages": "messages", "stream": "stream"},
            output_key="reasoning_result",
        ),
    )
    builder.add_edge("prompt", "ask")

    def unpack(st):
        q = st["reasoning_result"]["response"]["choices"][0]["message"][
            "content"
        ].strip()
        yield {"question": q}

    builder.add_node("unpack", unpack)
    builder.add_edge("ask", "unpack")

    def pause_step(st):
        run_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())

        # record open task
        tasks.insert_one(
            {
                "_id": task_id,
                "run_id": run_id,
                "question": st["question"],
                "status": "open",
                "created": datetime.utcnow(),
            }
        )

        # deep copy state before persisting
        frozen = copy.deepcopy(st)
        save_run(run_id, "human_quiz", frozen, next_node="grade")

        yield {
            "pause": True,
            "run_id": run_id,
            "task_id": task_id,
            "question": st["question"],
            "state": frozen,
            "next_node": "grade",
        }

    builder.add_node("pause_step", pause_step)
    builder.add_edge("unpack", "pause_step")  # stop here (no edge to END!)

    app = builder.compile()
    yield from run_flow(app, state, stream)


# ─────────── Phase-2  (resume, grade) --------------------------------------------------------------


def resume(state: Dict[str, Any], next_node: str) -> Dict[str, Any]:
    """
    Mini-graph that starts at “grade”, generates feedback, and returns
    the final state.  The caller (async_agent_handler) will persist the
    returned state so that `feedback` is stored in flow_runs.
    """
    builder = StateGraph(QuizState)

    # node: craft grading prompt
    def grade_prompt(st):
        q = st["question"]
        a = (st.get("async_result", {}) or {}).get("answer", "")
        prompt = (
            "Here is a quiz question and a student's answer.\n\n"
            f"Question: {q}\nAnswer: {a}\n\n"
            "Give concise feedback and specify if it is correct."
        )
        yield {"messages": [{"role": "user", "content": prompt}]}

    builder.add_node("grade", grade_prompt)

    # node: call LLM for feedback
    builder.add_node(
        "reason",
        reasoning_completion_node(
            input_key_map={"messages": "messages", "stream": "stream"},
            output_key="feedback",
        ),
    )

    # linear wiring
    builder.add_edge(START, "grade")
    builder.add_edge("grade", "reason")
    builder.add_edge("reason", END)

    app = builder.compile()

    # invoke returns the final state dict; return it to caller
    return app.invoke(state)
