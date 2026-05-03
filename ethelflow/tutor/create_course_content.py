# -*- coding: utf-8 -*-
"""
Created on Thu Apr 16 16:25:13 2026

@author: oppna
"""

# create course content
import json
import pandas as pd

def to_json(x) -> str:
    return json.dumps(x, ensure_ascii=False)

def add_topic_rows(
    rows,
    *,
    course_id,
    topic,
    lesson_text,
    key_points,
    examples,
    questions
):
    # lesson_text row
    rows.append({
        "course_id": course_id,
        "topic_id": topic["topic_id"],
        "topic_title": topic["title"],
        "order": topic["order"],
        "prerequisites": to_json(topic["prerequisites"]),
        "content_id": f'{topic["topic_id"]}__lesson_text',
        "type": "lesson_text",
        "text": lesson_text,
        "answer_key": None,
        "rubric": None,
    })

    # key_points rows
    for i, kp in enumerate(key_points, start=1):
        rows.append({
            "course_id": course_id,
            "topic_id": topic["topic_id"],
            "topic_title": topic["title"],
            "order": topic["order"],
            "prerequisites": to_json(topic["prerequisites"]),
            "content_id": f'{topic["topic_id"]}__kp_{i:02d}',
            "type": "key_point",
            "text": kp,
            "answer_key": None,
            "rubric": None,
        })

    # examples rows
    for i, ex in enumerate(examples, start=1):
        rows.append({
            "course_id": course_id,
            "topic_id": topic["topic_id"],
            "topic_title": topic["title"],
            "order": topic["order"],
            "prerequisites": to_json(topic["prerequisites"]),
            "content_id": f'{topic["topic_id"]}__ex_{i:02d}',
            "type": "example",
            "text": ex,
            "answer_key": None,
            "rubric": None,
        })

    # question rows
    for q in questions:
        rows.append({
            "course_id": course_id,
            "topic_id": topic["topic_id"],
            "topic_title": topic["title"],
            "order": topic["order"],
            "prerequisites": to_json(topic["prerequisites"]),
            "content_id": f'{topic["topic_id"]}__{q["question_id"]}',
            "type": "quiz_question",
            "text": q["question_text"],
            "answer_key": to_json(q["answer_key"]),
            "rubric": to_json(q["rubric"]),
        })


rows = []
course_id = "plant_biology_101"

# -------- First lesson --------
topic_1 = {
    "topic_id": "cell_basics_prok_vs_euk",
    "title": "Prokaryotes vs Eukaryotes",
    "order": 1,
    "prerequisites": [],
}

lesson_text_1 = """Of all the types of cells revealed by the microscope, bacteria have the simplest structure..."""

key_points_1 = [
    "Classification is based on presence/absence of a nucleus.",
    "Eukaryotes have a nucleus; prokaryotes lack a nucleus.",
    "Prokaryotes include bacteria and archaea."
]

examples_1 = [
    "Classify bacteria and archaea as prokaryotes; plants and animals as eukaryotes.",
]

questions_1 = [
    {
        "question_id": "q1",
        "question_text": "Define eukaryotes and prokaryotes, and state the key feature used to classify them.",
        "answer_key": {
            "required_points": [
                "Classification is based on presence/absence of a nucleus",
                "Eukaryotes have a nucleus",
                "Prokaryotes lack a nucleus",
            ]
        },
        "rubric": {
            "max_score": 3,
            "criteria": [
                {"id": "c1", "desc": "Mentions nucleus presence/absence as basis", "points": 1},
                {"id": "c2", "desc": "Correctly defines eukaryotes", "points": 1},
                {"id": "c3", "desc": "Correctly defines prokaryotes", "points": 1},
            ],
            "common_mistakes": [
                "Says prokaryotes lack DNA (they lack a nucleus)",
            ],
        },
    },
]

add_topic_rows(
    rows,
    course_id=course_id,
    topic=topic_1,
    lesson_text=lesson_text_1,
    key_points=key_points_1,
    examples=examples_1,
    questions=questions_1
)

# -------- Second lesson --------
topic_2 = {
    "topic_id": "plant_cell_structure",
    "title": "Plant Cell Structure",
    "order": 2,
    "prerequisites": ["cell_basics_prok_vs_euk"],
}

lesson_text_2 = """
Plant cells are eukaryotic cells with several structures that distinguish them from animal cells.
Like other eukaryotes, they contain a nucleus and membrane-bound organelles. In addition, plant
cells have a rigid cell wall made mainly of cellulose, chloroplasts for photosynthesis, and a
large central vacuole that helps maintain turgor pressure and stores water and dissolved substances.
"""

key_points_2 = [
    "Plant cells are eukaryotic and therefore contain a nucleus.",
    "The cell wall provides support and protection.",
    "Chloroplasts carry out photosynthesis.",
    "The large central vacuole stores water and helps maintain cell pressure."
]

examples_2 = [
    "A leaf cell contains chloroplasts because it performs photosynthesis.",
    "The central vacuole helps a plant cell stay rigid by maintaining turgor pressure.",
]

questions_2 = [
    {
        "question_id": "q1",
        "question_text": "Name three structures that distinguish plant cells from animal cells and briefly state their functions.",
        "answer_key": {
            "required_points": [
                "Cell wall provides support/protection",
                "Chloroplasts perform photosynthesis",
                "Large central vacuole stores water and maintains turgor pressure",
            ]
        },
        "rubric": {
            "max_score": 3,
            "criteria": [
                {"id": "c1", "desc": "Mentions cell wall and its function", "points": 1},
                {"id": "c2", "desc": "Mentions chloroplasts and their function", "points": 1},
                {"id": "c3", "desc": "Mentions central vacuole and its function", "points": 1},
            ],
            "common_mistakes": [
                "Says animal cells have chloroplasts",
                "Confuses cell wall with cell membrane",
            ],
        },
    },
]

add_topic_rows(
    rows,
    course_id=course_id,
    topic=topic_2,
    lesson_text=lesson_text_2,
    key_points=key_points_2,
    examples=examples_2,
    questions=questions_2
)

DF_COURSE = pd.DataFrame(rows)