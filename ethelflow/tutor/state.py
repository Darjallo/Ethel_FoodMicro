# -*- coding: utf-8 -*-
"""
Created on Wed Apr 29 22:50:17 2026

@author: oppna
"""


from typing import TypedDict, Dict, Any, Optional, List

class TutorState(TypedDict, total=False):
    # required
    tenant: str 
    #reasoning_effort: Optional[str]   # ?

    # tutor
    subject: str
    student_level: str
    goals: str
    course_id: str
    current_topic_id: str
    topic_order: list[str]
    
    # instead of llm.invoke
    router_prompt: str
    router_raw_output: str
    
    tutor_prompt: str
    tutor_raw_output: str
    
    quiz_prompt: str
    quiz_raw_output: str
    
    grading_prompt: str
    grading_raw_output: str
    grading_result: Dict[str, Any]
    #

    quit: bool
    last_analysis: Dict[str, Any]

    history: List[Dict[str, str]]  # list of langchain messages # changed from Any to str
    last_user_msg: str

    # Learning model
    mastery: Dict[str, float]  # topic_id -> 0..1

    # Quiz + rewards
    pending_quiz: Optional[Dict[str, Any]]
    last_quiz_score: Optional[float]

    # Quick check
    awaiting_check: bool
    last_check_question: str
    last_check_question_id: Optional[str]   # NEW (important)

    asked_question_ids: list[str]           # NEW (optional but recommended)

    coins: int
    coins_awarded_last: int

    # Output to display
    draft_response: str
    response_type: str  # "lesson" | "tutor" | "quiz" | "progress" | ...

    check_attempts: int
    ready_to_advance: bool