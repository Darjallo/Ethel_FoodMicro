# -*- coding: utf-8 -*-
"""
Created on Thu Apr 16 17:21:51 2026

@author: oppna
"""

from typing import Dict, Any, Optional, List
import random
import json
import pandas as pd
from langchain_core.messages import SystemMessage

from ethelflow.tutor.state import TutorState 
from ethelflow.tutor.course_registry import PROVIDERS, COURSE, PASS_SCORE, MAX_WRONG_ATTEMPTS
from ethelflow.tutor.course_registry import get_provider
# from llm_init import llm



def _advance_to_next_topic(state: TutorState) -> None:
    """Advance current_topic_id to the next id in topic_order if possible."""
    topic_order = state.get("topic_order", [])  # get safely returns None or default value
    cur = state["current_topic_id"]

    try:
        idx = topic_order.index(cur)
    except ValueError:
        # If current topic not in topic_order, fall back to first topic if possible
        if topic_order:
            state["current_topic_id"] = topic_order[0]
            state["mastery"].setdefault(state["current_topic_id"], 0.0)
        return

    if idx + 1 < len(topic_order):
        nxt = topic_order[idx + 1]
        state["current_topic_id"] = nxt
        state["mastery"].setdefault(nxt, 0.0)

def get_course(state: TutorState) -> dict:
    # Single-course prototype: always return the one COURSE
    if state.get("course_id") and state["course_id"] != COURSE["course_id"]:
        raise KeyError(f"State course_id='{state['course_id']}' doesn't match loaded COURSE='{COURSE['course_id']}'")
    return COURSE

def get_topic(course: dict, topic_id: str) -> dict:
    topics = course.get("topics", [])
    for t in topics:
        # t must be a dict; if it's not, your COURSE["topics"] isn't the right structure
        if isinstance(t, dict) and t.get("topic_id") == topic_id:
            return t
    raise KeyError(f"topic_id '{topic_id}' not found. Available: {[x.get('topic_id') for x in topics if isinstance(x, dict)]}")


def _pick_quick_check(questions: List[Dict[str, Any]], asked_ids: set) -> Optional[Dict[str, Any]]:
    """Prefer an unseen question; fallback to first available."""
    if not questions:
        return None
    unseen = [q for q in questions if q.get("content_id") not in asked_ids]
    return random.choice(unseen) if unseen else random.choice(questions)


def ordered_topic_ids(course: dict) -> list[str]:
    """
    Return topic_ids sorted by their 'order' field.
    """
    topics = sorted(course["topics"], key=lambda t: t.get("order", 10**3))
    return [t["topic_id"] for t in topics]

def get_next_topic_id(course: dict, current_topic_id: str):
    """
    Return the next topic_id based on course order,
    or None if the current topic is the last one.
    """
    ids = ordered_topic_ids(course)

    if current_topic_id not in ids:
        raise KeyError(
            f"current_topic_id '{current_topic_id}' not in course topics: {ids}"
        )

    idx = ids.index(current_topic_id)

    if idx + 1 < len(ids):
        return ids[idx + 1]

    return None  # last topic reached

def get_question_by_id(self, content_id: str) -> Optional[Dict[str, Any]]:
    sub = self.df[(self.df["content_id"] == content_id) & (self.df["type"] == "quiz_question")]
    if sub.empty:
        return None
    r = sub.iloc[0]
    return {
        "content_id": r["content_id"],
        "topic_id": r["topic_id"],
        "question_text": r["text"],
        "answer_key": json.loads(r["answer_key"]) if pd.notna(r["answer_key"]) else None,
        "rubric": json.loads(r["rubric"]) if pd.notna(r["rubric"]) else None,
    }


def format_correct_answer(answer_key: dict) -> str:
    req = (answer_key or {}).get("required_points") or []
    if isinstance(req, list) and req:
        return "Correct answer (key points):\n- " + "\n- ".join(req)
    return "Correct answer: (not available)"



# def analyze_and_update_state(user_text: str, state: "TutorState") -> "TutorState":
    
#     print("DEBUG awaiting_check:", state.get("awaiting_check"))
#     print("DEBUG pending_quiz:", state.get("pending_quiz"))
#     print("DEBUG last_check_question_id:", state.get("last_check_question_id"))
#     print("DEBUG current_topic_id:", state.get("current_topic_id"))
#     print("DEBUG mastery before:", state["mastery"].get(state["current_topic_id"], 0.0))

#     text = user_text.strip()

#     if text.lower() in {"q", "quit", "exit"}:
#         state["quit"] = True
#         state["last_analysis"] = {"intent": "quit"}
#         return state

#     provider = get_provider(state)
#     topic_id = state["current_topic_id"]
#     current_mastery = state["mastery"].get(topic_id, 0.0)

#     # --- Quick check grading path ---
#     if state.get("awaiting_check") and not state.get("pending_quiz"):
#         qid = state.get("last_check_question_id")
#         if not qid:
#             state["awaiting_check"] = False
#             state["last_check_question"] = ""
#             state["last_check_question_id"] = None
#             state["last_analysis"] = {
#                 "intent": "quick_check_answer",
#                 "score": 0.0,
#                 "feedback": "Internal error: missing question id.",
#                 "mastery_before": current_mastery,
#                 "mastery_after": current_mastery,
#             }
#             state["response_type"] = "new_lesson"
#             return state

#         q = provider.get_question_by_id(qid)
#         if not q:
#             state["awaiting_check"] = False
#             state["last_check_question"] = ""
#             state["last_check_question_id"] = None
#             state["last_analysis"] = {
#                 "intent": "quick_check_answer",
#                 "score": 0.0,
#                 "feedback": "Internal error: question not found.",
#                 "mastery_before": current_mastery,
#                 "mastery_after": current_mastery,
#             }
#             state["response_type"] = "new_lesson"
#             return state

#         # Safe topic title lookup
#         topic_meta = next((t for t in provider.list_topics() if t["topic_id"] == topic_id), None)
#         topic_title = topic_meta["title"] if topic_meta else topic_id

#         rubric = q.get("rubric") or {}
#         answer_key = q.get("answer_key") or {}

#         prompt = f"""
# You are grading a student's short answer to a course quick-check question.

# TOPIC: {topic_title}

# QUESTION: {q["question_text"]}
# STUDENT ANSWER: {text}

# ANSWER KEY (concept points):
# {json.dumps(answer_key, ensure_ascii=False, indent=2)}

# RUBRIC (how to score):
# {json.dumps(rubric, ensure_ascii=False, indent=2)}

# Instructions:
# - Judge semantic correctness, not exact phrasing.
# - Evaluate each rubric criterion as: "met", "partial", or "not_met".
# - Provide evidence by quoting a short fragment from the student's answer (or empty if none).
# - Identify the main mistake (if any) and explain it briefly.

# Return JSON only in exactly this schema:
# {{
#   "criterion_results": [
#     {{"id": "<criterion_id>", "result": "met|partial|not_met", "evidence": "<short quote or empty>"}}
#   ],
#   "score": <float 0..1>,
#   "brief_feedback": "<one short sentence>",
#   "error_explanation": "<1-3 sentences, empty if fully correct>"
# }}
# """
#         raw = llm.invoke([SystemMessage(content=prompt)]).content.strip()

#         try:
#             data = json.loads(raw)
#             score = float(data.get("score", 0.0))
#         except Exception:
#             data = {
#                 "criterion_results": [],
#                 "score": 0.0,
#                 "brief_feedback": "Couldn't grade reliably; try rephrasing your answer.",
#                 "error_explanation": ""
#             }
#             score = 0.0

#         score = max(0.0, min(1.0, score))
#         print('score = ', score)

#         # update attempts
#         state["check_attempts"] = state.get("check_attempts", 0) + 1

#         passed = score >= PASS_SCORE  # passed is boolean
#         forced_reveal = False

#         if passed:
#             # mastery update on success
#             new_mastery = max(0.0, min(1.0, current_mastery + score))   # a clever function defining knowledge accumulation can be introduced here
#             state["mastery"][topic_id] = new_mastery
            
#             awarded = 0
#             if new_mastery >= 0.8:
#                 awarded = 5
#             elif new_mastery >= 0.6:
#                 awarded = 2

#             state["coins"] = state.get("coins", 0) + awarded
#             state["coins_awarded_last"] = awarded
            
#             state["awaiting_check"] = False
#             state["last_check_question"] = ""
#             state["last_check_question_id"] = None
#             state["check_attempts"] = 0

#             state["ready_to_advance"] = True

#             state["last_analysis"] = {
#                 "intent": "quick_check_answer",
#                 "score": score,
#                 "feedback": data.get("brief_feedback", ""),
#                 "error_explanation": data.get("error_explanation", ""),
#                 "criterion_results": data.get("criterion_results", []),
#                 "question_id": qid,
#                 "mastery_before": current_mastery,
#                 "mastery_after": new_mastery,
#                 "passed": True,
#             }

#             # let planner decide next (lesson/quiz/advance)
#             state["response_type"] = "new_lesson"
#             return state

#         # wrong answer
#         if state["check_attempts"] >= MAX_WRONG_ATTEMPTS:
#             forced_reveal = True
#             correct_text = format_correct_answer(answer_key)

#             # optional: small mastery bump (or leave unchanged)
#             new_mastery = current_mastery
#             state["mastery"][topic_id] = new_mastery

#             state["awaiting_check"] = False
#             state["last_check_question"] = ""
#             state["last_check_question_id"] = None
#             state["check_attempts"] = 0

#             state["ready_to_advance"] = True

#             state["last_analysis"] = {
#                 "intent": "quick_check_answer",
#                 "score": score,
#                 "feedback": data.get("brief_feedback", ""),
#                 "error_explanation": data.get("error_explanation", ""),
#                 "criterion_results": data.get("criterion_results", []),
#                 "question_id": qid,
#                 "mastery_before": current_mastery,
#                 "mastery_after": new_mastery,
#                 "passed": False,
#                 "forced_reveal": True,
#             }

#             state["draft_response"] = (
#                 f"Not quite.\n\n"
#                 f"{data.get('brief_feedback','')}\n\n"
#                 f"{data.get('error_explanation','')}\n\n"
#                 f"✅ {correct_text}\n\n"
#                 f"Let’s move on to the next topic."
#             )
#             state["response_type"] = "reveal_and_advance"
#             return state

#         # wrong but still has attempts left: retry
#         state["ready_to_advance"] = False
#         state["last_analysis"] = {
#             "intent": "quick_check_answer",
#             "score": score,
#             "feedback": data.get("brief_feedback", ""),
#             "error_explanation": data.get("error_explanation", ""),
#             "criterion_results": data.get("criterion_results", []),
#             "question_id": qid,
#             "mastery_before": current_mastery,
#             "mastery_after": current_mastery,
#             "passed": False,
#             "attempt": state["check_attempts"],
#         }

#         state["draft_response"] = (
#             f"{data.get('brief_feedback','Not quite.')}\n\n"
#             f"{data.get('error_explanation','')}\n\n"
#             f"Try again: **{q['question_text']}**"
#         )
#         state["response_type"] = "retry_check"
#         return state

#     return state


def init_state(
    subject: str="Plant Biology",
    level: str="high school",
    goals: str="prepare for exams",
    course_id: str="plant_biology_101",
    ) -> TutorState:

    provider = PROVIDERS[course_id]
    topics = provider.list_topics()
    if not topics:
        raise ValueError(f"No topics found for course_id={course_id!r}")
    topic_order = [t["topic_id"] for t in topics]
    first_topic_id = topic_order[0]


    return TutorState(
        course_id=course_id,

        #content_provider=provider,
        asked_question_ids=[],
        current_topic_id=first_topic_id,
        topic_order=topic_order, 

        subject=subject,
        student_level=level,
        goals=goals,

        history=[],
        last_user_msg="",

        mastery={first_topic_id: 0.0},

        pending_quiz=None,
        last_quiz_score=None,

        coins=0,
        coins_awarded_last=0,

        draft_response=(
            "## 👋 Welcome\n"
            "Hello! I’m your tutor.\n"
            "Are you ready to start a new lesson?"
        ),
        response_type="greeting",

        quit=False,
        last_analysis={},

        awaiting_check=False,
        last_check_question="",

        check_attempts=0,
        ready_to_advance=False,

    )

