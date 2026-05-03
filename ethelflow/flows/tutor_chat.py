# -*- coding: utf-8 -*-
"""
Created on Mon Apr 27 13:16:14 2026

@author: oppna
"""

from typing import TypedDict, Dict, Any, Optional, List, Literal
import uuid
from langgraph.graph import StateGraph, END


from ethelflow.agents.reasoning.node_adapter import reasoning_node
from ethelflow.tutor.state import TutorState 
from ethelflow.tutor.helpers import _advance_to_next_topic, _pick_quick_check
from ethelflow.tutor.course_registry import get_provider
    
 
    
async def run(
    thread_id: uuid.UUID,
    context=None,
    stream: bool = False,
    checkpointer=None,
    command=None,
):
    """
    Flow: tutor_chat

    Input: canonical context dict (caller owns memory)
    Output (non-stream): dict with:
      - answer (str)
      - context (updated canonical context)
      - intent metadata
    """
    context = context or {}
    if not isinstance(context, dict):
        raise ValueError("context must be a dict")
    
    #if command is not None:
     #   raise ValueError("This tutor flow does not support resume/command yet")
        
    def build_initial_state(context: dict) -> TutorState:
        tenant = context.get("tenant")
        if not isinstance(tenant, str) or not tenant.strip():
            raise ValueError("Missing or invalid 'tenant' in context")
    
        course_id = context.get("course_id", "plant_biology_101")
        if not isinstance(course_id, str) or not course_id.strip():
            raise ValueError("Missing or invalid 'course_id' in context")
    
        user_message = context.get("user_message")
        if user_message is None:
            user_message = context.get("input", "")
        if not isinstance(user_message, str):
            raise ValueError("'user_message' or 'input' must be a string")
    
        subject = context.get("subject", "Plant Biology")
        student_level = context.get("student_level", "high school")
        goals = context.get("goals", "prepare for exams")
    
        provider = get_provider({"course_id": course_id})
        topics = provider.list_topics()
        if not topics:
            raise ValueError(f"No topics found for course_id={course_id!r}")
    
        topic_order = [t["topic_id"] for t in topics]
        first_topic_id = topic_order[0]
    
        current_topic_id = context.get("current_topic_id", first_topic_id)
        if current_topic_id not in topic_order:
            current_topic_id = first_topic_id
    
        mastery = context.get("mastery")
        if not isinstance(mastery, dict):
            mastery = {current_topic_id: 0.0}
        else:
            mastery.setdefault(current_topic_id, 0.0)
    
        history = context.get("history")
        if not isinstance(history, list):
            history = []
    
        return TutorState(
            tenant=tenant.strip(),
            subject=subject,
            student_level=student_level,
            goals=goals,
            course_id=course_id,
            current_topic_id=current_topic_id,
            topic_order=topic_order,
            router_prompt="",
            router_raw_output="",
            tutor_prompt="",
            tutor_raw_output="",
            quiz_prompt="",
            quiz_raw_output="",
            grading_prompt="",
            grading_raw_output="",
            grading_result={},
            quit=False,
            last_analysis={},
            history=history,
            last_user_msg=user_message,
            mastery=mastery,
            pending_quiz=None,
            last_quiz_score=None,
            awaiting_check=False,
            last_check_question="",
            last_check_question_id=None,
            asked_question_ids=[],
            coins=0,
            coins_awarded_last=0,
            draft_response="",
            response_type="",
            check_attempts=0,
            ready_to_advance=False,
        )
        
    # functions for nodes
    def router_prompt_node(state: TutorState) -> TutorState:
        print("DEBUG entered router_prompt_node", flush=True)
        user = state["last_user_msg"].strip().lower()
        print("DEBUG router user =", user, flush=True)
        if user in {"yes", "y", "ready", "let's start", "lets start", "start", "sure", "ok"}:
            state["response_type"] = "new_lesson"
            state["router_prompt"] = ""
            print("DEBUG router response_type before =", state.get("response_type"), flush=True)
            return state

        prompt = f"""
        You are an intent router for a proactive tutor.
        Classify the user's message into exactly one label:
        - "question": asking for explanation, help, confusion, why/how
        - "new_lesson": asks to learn something new or continue lesson
        - "meta": asks about progress, coins, plan, what next, schedule, review
        - "quiz_request": asks for quiz/test/practice questions or demonstrates readiness for a test
        
        Return ONLY the label.
        Message: {user}
        """
        
        state["router_prompt"] = prompt
        print("DEBUG router response_type before prompt =", state.get("response_type"), flush=True)
        return state
    
    
    def router_label_node(state: TutorState) -> TutorState:
        print("DEBUG entered router_label_node", flush=True)
        label = (state.get("router_raw_output") or "").strip().lower()
        if label not in {"question","new_lesson","meta","quiz_request"}:
            label = "question"
        state["response_type"] = label
        print("DEBUG parsed label =", label, flush=True)
        return state
    
    def planner_node(state: TutorState) -> TutorState:
        print("DEBUG entered planner_node", flush=True)
        label = state.get("response_type", "")
        topic_id = state["current_topic_id"]
        mastery = state["mastery"].get(topic_id, 0.0)

        # 1) Advance topic if either:
        #    - mastery high enough, OR
        #    - grading forced reveal after 2 wrong answers and set ready_to_advance=True
        if state.get("ready_to_advance") or mastery >= 0.80:
            _advance_to_next_topic(state)
            state["ready_to_advance"] = False  # consume the flag

            # If we just revealed answer and want to continue immediately,
            # we can force next action to be a lesson in the new topic.
            if label == "reveal_and_advance":
                state["response_type"] = "lesson"
                return state

        # 2) Decide what node to run next (simple heuristic)
        if label == "quiz_request":
            state["response_type"] = "quiz"
        elif label == "meta":
            state["response_type"] = "progress"
        elif label == "question":
            state["response_type"] = "tutor"
        elif label in {"retry_check", "reveal_and_advance"}:
            # These labels already have a draft_response prepared in analyze_and_update_state.
            # We should NOT overwrite it with a lesson.
            # You can route to a formatter/output node, or just leave response_type as-is.
            state["response_type"] = label
        else:
            # default: give lesson for current topic
            state["response_type"] = "lesson"

        return state
    
    
    def lesson_node(state: "TutorState") -> "TutorState":
        print("DEBUG entered lesson_node", flush=True)
        topic_id = state["current_topic_id"]
        print("DEBUG lesson topic_id =", topic_id, flush=True)
        provider = get_provider(state)

        # ---- Safe topic lookup (avoid StopIteration) ----
        topic_meta = next((t for t in provider.list_topics() if t["topic_id"] == topic_id), None)
        if not topic_meta:
            available = [t["topic_id"] for t in provider.list_topics()]
            state["awaiting_check"] = False
            state["last_check_question"] = ""
            state["last_check_question_id"] = None
            state["draft_response"] = (
                f"⚠️ Unknown topic_id: `{topic_id}`\n\n"
                f"Available topics: {available}\n\n"
                f"Fix: set `state['current_topic_id']` to one of the available ids."
            )
            state["response_type"] = "error"
            return state

        topic_title = topic_meta["title"]

        # ---- Pull content from provider ----
        materials = provider.get_materials(topic_id)
        questions = provider.get_questions(topic_id)

        # ---- Ensure asked_question_ids exists ----
        asked_ids = set(state.get("asked_question_ids", []))

        quick_check = _pick_quick_check(questions, asked_ids)

        if quick_check:
            state["awaiting_check"] = True
            state["last_check_question"] = quick_check["question_text"]
            state["last_check_question_id"] = quick_check["content_id"]
            asked_ids.add(quick_check["content_id"])
            state["asked_question_ids"] = list(asked_ids)
        else:
            state["awaiting_check"] = False
            state["last_check_question"] = ""
            state["last_check_question_id"] = None

        # Optional: include 1 example (keeps lesson compact)
        example_line = ""
        if materials.get("examples"):
            example_line = f"\n\n**Example:** {materials['examples'][0]}"

        # Build response
        key_points = materials.get("key_points", [])
        key_points_block = ""
        if key_points:
            key_points_block = "**Key points:**\n- " + "\n- ".join(key_points)

        quick_check_block = ""
        if quick_check:
            quick_check_block = f"\n\n**Quick check:** {state['last_check_question']}"

        state["draft_response"] = (
            f"### {topic_title}\n\n"
            f"{materials.get('lesson_text','')}\n\n"
            f"{key_points_block}"
            f"{example_line}"
            f"{quick_check_block}"
        ).strip()

        state["response_type"] = "lesson"
        return state
    
    def progress_node(state: "TutorState") -> "TutorState":
        topic_id = state["current_topic_id"]  # <-- replace current_topic
        mastery = state["mastery"].get(topic_id, 0.0)

        # Look up a friendly topic title (optional, but nicer UX)
        topic_title = topic_id
        try:
            provider = get_provider(state)
            topic_meta = next((t for t in provider.list_topics() if t["topic_id"] == topic_id), None)
            if topic_meta:
                topic_title = topic_meta["title"]
        except Exception:
            pass  # fallback: show topic_id if provider not available


        state["draft_response"] = (
            f"**Progress**\n\n"
            f"- Topic: **{topic_title}**\n"
            f"- Estimated mastery: **{mastery:.2f} / 1.00**\n"
            f"- Total coins: **{state['coins']}**\n\n"
            f"Tell me if you want a quiz or to continue with the next lesson block."
        )
        state["response_type"] = "progress"
        return state
    
    def formatter_node(state: TutorState) -> TutorState:
        # Add a small header depending on type
        t = state["response_type"]
        header = {
            "lesson": "📘 Lesson",
            "tutor": "🤝 Tutor Help",
            "quiz": "🧠 Quick Quiz",
            "progress": "🏁 Progress",
        }.get(t, "📝")

        state["draft_response"] = f"\n## {header}\n\n{state['draft_response']}"
        print("DEBUG formatter response =", state['draft_response'], flush=True)
        return state

    
    initial_state = build_initial_state(context)
    
    workflow = StateGraph(TutorState)

    workflow.add_node("router_prompt", router_prompt_node)
    workflow.add_node(
        "router_reasoning",
        reasoning_node(
            tenant_key="tenant",
            prompt_key="router_prompt",
            reasoning_effort_key=None, #"reasoning_effort",
            stream_key=None,  # don't stream this node; easier for interrupt parsing
            output_key="router_raw_output",
        ),
    )
    workflow.add_node("router_label", router_label_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("lesson", lesson_node)
    #workflow.add_node("tutor", tutor_node)
    #workflow.add_node("quiz", quiz_node)
    workflow.add_node("progress", progress_node)
    workflow.add_node("formatter", formatter_node)
    
    workflow.set_entry_point("router_prompt")
    # workflow.add_edge("router_prompt", "router_reasoning")
   #  workflow.add_edge("router_reasoning", "router_label")
    # workflow.add_edge("router_label", "planner")
    def route_after_router_prompt(state: TutorState) -> Literal["router_reasoning", "planner"]:
        if state.get("response_type") == "new_lesson":
            return "planner"
        return "router_reasoning"
    
    workflow.add_conditional_edges(
        "router_prompt",
        route_after_router_prompt,
        {
            "router_reasoning": "router_reasoning",
            "planner": "planner",
        },
    )

    workflow.add_edge("router_reasoning", "router_label")
    workflow.add_edge("router_label", "planner")
    
    def route_from_planner(state: TutorState) -> Literal["lesson","progress"]: #"tutor","quiz",
        rt = state["response_type"]
        if rt in {"lesson","progress"}: # "tutor","quiz",
            return rt
        return "lesson" #"tutor"

    workflow.add_conditional_edges("planner", route_from_planner, {
        "lesson": "lesson",
        # "tutor": "tutor",
        # "quiz": "quiz",
        "progress": "progress",
    })

    for n in ["lesson","progress"]:  # "tutor","quiz",
        workflow.add_edge(n, "formatter")

    workflow.add_edge("formatter", END)

    app = workflow.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": str(thread_id)}}
    
    print("HELLO I AM HERE", flush=True)
    
    out = await app.ainvoke(initial_state, config=config)
    print("DEBUG tutor out =", out, flush=True)
    yield {
            "answer": out.get("draft_response", ""),
            "response_type": out.get("response_type", ""),
            "current_topic_id": out.get("current_topic_id"),
            "awaiting_check": out.get("awaiting_check", False),
            "last_check_question": out.get("last_check_question", ""),
            "last_check_question_id": out.get("last_check_question_id"),
            "mastery": out.get("mastery", {}),
            "coins": out.get("coins", 0),
            "context": {
                "tenant": out.get("tenant"),
                "course_id": out.get("course_id"),
                "subject": out.get("subject"),
                "student_level": out.get("student_level"),
                "goals": out.get("goals"),
                "current_topic_id": out.get("current_topic_id"),
                "topic_order": out.get("topic_order", []),
                "mastery": out.get("mastery", {}),
                "coins": out.get("coins", 0),
                "awaiting_check": out.get("awaiting_check", False),
                "last_check_question": out.get("last_check_question", ""),
                "last_check_question_id": out.get("last_check_question_id"),
                "asked_question_ids": out.get("asked_question_ids", []),
                "history": out.get("history", []),
            },
        }

    # if stream:
    #     print("in stream", flush=True)
    #     async for event in app.astream_events(initial_state, config=config, version="v2"):
    #         print("DEBUG stream event =", event, flush=True)
    #         yield str(event)
    # else:
    #     print("in ELSE", flush=True)
    #     try:
    #         out = await app.ainvoke(initial_state, config=config)
    #         print("DEBUG tutor out =", out, flush=True)
    #     except Exception as e:
    #         print("DEBUG app.ainvoke EXCEPTION =", repr(e), flush=True)
    #         raise
        
    #     # out = await app.ainvoke(initial_state, config=config)
    #     # print("DEBUG tutor out =", out, flush=True)
    #     yield {
    #         "answer": out.get("draft_response", ""),
    #         "response_type": out.get("response_type", ""),
    #         "current_topic_id": out.get("current_topic_id"),
    #         "awaiting_check": out.get("awaiting_check", False),
    #         "last_check_question": out.get("last_check_question", ""),
    #         "last_check_question_id": out.get("last_check_question_id"),
    #         "mastery": out.get("mastery", {}),
    #         "coins": out.get("coins", 0),
    #         "context": {
    #             "tenant": out.get("tenant"),
    #             "course_id": out.get("course_id"),
    #             "subject": out.get("subject"),
    #             "student_level": out.get("student_level"),
    #             "goals": out.get("goals"),
    #             "current_topic_id": out.get("current_topic_id"),
    #             "topic_order": out.get("topic_order", []),
    #             "mastery": out.get("mastery", {}),
    #             "coins": out.get("coins", 0),
    #             "awaiting_check": out.get("awaiting_check", False),
    #             "last_check_question": out.get("last_check_question", ""),
    #             "last_check_question_id": out.get("last_check_question_id"),
    #             "asked_question_ids": out.get("asked_question_ids", []),
    #             "history": out.get("history", []),
    #         },
    #     }