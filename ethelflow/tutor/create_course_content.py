# -*- coding: utf-8 -*-
"""
Create course content for the Ethel tutor flow.

This file replaces the previous plant-biology example course with five lessons
on bovine udder anatomy, milk synthesis, colostrum, SCC, and milk spoilage.

The schema follows the original create_course_content.py structure:
- one lesson_text row per topic
- optional key_point rows
- optional example rows
- one quiz_question row per topic

"""

import json
from pathlib import Path
import pandas as pd


def to_json(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def figure_markdown(alt_text: str, filename: str) -> str:
    """Return Markdown for a figure stored under the configured asset route."""
    return f"![{alt_text}]({FIGURE_ASSET_BASE_URL}/{filename})"


def add_topic_rows(
    rows,
    *,
    course_id,
    topic,
    lesson_text,
    key_points,
    examples,
    questions,
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


# Change this path to match the public/static route used by your frontend.
# Example alternatives:
#   "/assets/bovine_milk_101/figures"
#   "/assets/ethz/bovine_milk_101/figures"
#   "http://localhost:8080/assets/bovine_milk_101/figures"
FIGURE_ASSET_BASE_URL = "/assets/figs_for_lessons"

FIGURE_SOURCE_PATHS = {
    "l1f1.png": r"C:\Users\oppna\Documents\LMU\Tutor\Ethel\figs_for_lessons\l1f1.png",
    "l2f1.png": r"C:\Users\oppna\Documents\LMU\Tutor\Ethel\figs_for_lessons\l2f1.png",
    "l3f1.png": r"C:\Users\oppna\Documents\LMU\Tutor\Ethel\figs_for_lessons\l3f1.png",
    "l4f1.png": r"C:\Users\oppna\Documents\LMU\Tutor\Ethel\figs_for_lessons\l4f1.png",
    "l5f1.png": r"C:\Users\oppna\Documents\LMU\Tutor\Ethel\figs_for_lessons\l5f1.png",
}

rows = []
# course_id = "bovine_milk_101"
course_id = "plant_biology_101"

lessons = [
    {
        "topic": {
            "topic_id": "bovine_udder_anatomy",
            "title": "Anatomy of the Bovine Udder",
            "order": 1,
            "prerequisites": [],
        },
        "content": (
            "The bovine udder is composed of four anatomically separate gland complexes known as quarters. "
            "Each quarter has its own independent duct system that leads to a gland cistern, which then leads "
            "to the teat cistern and finally the teat canal (streak canal). The teat canal serves as the primary "
            "barrier against ascending infections and is kept closed by smooth muscle (sphincter) and elastic fibers."
        ),
        "figure_alt": "Anatomy of the bovine udder",
        "figure_file": "l1f1.png",
        "key_points": [
            "The quarters are independent; an infection in one does not automatically mean the others are infected.",
            "The teat canal is the most critical anatomical defense against mastitis-causing pathogens.",
        ],
        "question": "Describe the basic internal plumbing of a cow's udder and its primary defense against infection.",
        "required_points": [
            "Four separate quarters",
            "Independent duct/cistern systems",
            "The teat canal (Ductus papillaris) is closed by smooth muscles and elastic fibers and acts as a barrier",
        ],
        "common_mistakes": [
            "Assumes that all four quarters share one common duct system",
            "Does not mention the teat canal as the main anatomical barrier",
        ],
    },
    {
        "topic": {
            "topic_id": "milk_synthesis_osmotic_balance",
            "title": "Milk Synthesis and Osmotic Balance",
            "order": 2,
            "prerequisites": ["bovine_udder_anatomy"],
        },
        "content": (
            "Lactose (milk sugar) is a highly specific disaccharide produced in the Golgi apparatus of alveolar "
            "epithelial cells. It is the most important osmotic component of milk. Because the osmotic pressure of "
            "milk must match that of blood, the secretion of lactose into the alveoli draws water into the milk until "
            "a concentration of roughly 4.5% to 5% is reached."
        ),
        "figure_alt": "Milk synthesis and osmotic balance",
        "figure_file": "l2f1.png",
        "key_points": [
            "The amount of lactose synthesized directly determines the total volume of milk produced.",
            "Synthesis is dependent on glucose taken up from the blood via the GLUT1 transporter.",
        ],
        "question": "How does the production of lactose influence the total volume of milk a cow produces?",
        "required_points": [
            "Lactose is osmotically active",
            "It draws water into the alveolar lumen",
            "Milk volume increases until osmotic balance between blood and milk is achieved",
        ],
        "common_mistakes": [
            "Describes lactose only as an energy source and ignores its osmotic role",
            "Does not connect lactose synthesis to water movement and milk volume",
        ],
    },
    {
        "topic": {
            "topic_id": "colostrum_passive_immunity",
            "title": "Colostrum and Passive Immunity",
            "order": 3,
            "prerequisites": ["milk_synthesis_osmotic_balance"],
        },
        "content": (
            "Colostrum is the first milk produced after birth, rich in nutrients and antibodies, particularly IgG1. "
            "Unlike humans, the bovine placenta does not allow antibodies to pass from the mother to the fetus. "
            "Consequently, calves are born without an active immune defense and must ingest colostrum within the "
            "first few hours of life to achieve passive immunization."
        ),
        "figure_alt": "Colostrum and passive immunity",
        "figure_file": "l3f1.png",
        "key_points": [
            "Calves are born immunologically passive and depend entirely on maternal antibodies from colostrum.",
            "Early intake is vital because the gut's ability to absorb these large molecules decreases rapidly after birth.",
        ],
        "question": "Why is it essential for a newborn calf to receive high-quality colostrum immediately after birth?",
        "required_points": [
            "No antibody transfer across the placenta",
            "The calf is born without immune protection",
            "Colostrum provides essential IgG1 antibodies for passive protection while the calf's own immune system matures",
        ],
        "common_mistakes": [
            "Assumes calves receive sufficient antibodies through the placenta before birth",
            "Mentions nutrition only and omits passive immune protection",
        ],
    },
    {
        "topic": {
            "topic_id": "somatic_cell_count_udder_health",
            "title": "Somatic Cell Count (SCC) and Udder Health",
            "order": 4,
            "prerequisites": ["colostrum_passive_immunity"],
        },
        "content": (
            "The Somatic Cell Count (SCC) is a primary indicator of udder health. These cells consist of epithelial "
            "cells and white blood cells (leukocytes), such as polymorphonuclear neutrophils (PMN). In a healthy "
            "quarter, the SCC should be below 100,000 cells/ml. During an infection (mastitis), the body floods the "
            "udder with PMNs to phagocytize pathogens, causing the SCC to rise drastically—sometimes to over "
            "10 million cells/ml in acute cases."
        ),
        "figure_alt": "Somatic cell count and udder health",
        "figure_file": "l4f1.png",
        "key_points": [
            "SCC is a sensitive sensor for secretory disturbances in the mammary gland.",
            "An increase in SCC, specifically PMNs, indicates the onset of an inflammatory reaction.",
        ],
        "question": "What does a high somatic cell count typically indicate, and which specific cell type is primarily responsible for the increase during acute inflammation?",
        "required_points": [
            "A high SCC indicates inflammation or infection (mastitis)",
            "The healthy threshold is below 100,000 cells/ml",
            "PMNs (neutrophils) are the primary cells that increase during the immune response",
        ],
        "common_mistakes": [
            "Treats SCC as a direct measure of bacteria rather than host cells",
            "Does not identify PMNs/neutrophils as the main cell type increasing during acute inflammation",
        ],
    },
    {
        "topic": {
            "topic_id": "spoilage_patterns_storage_temperature",
            "title": "Spoilage Patterns and Storage Temperature",
            "order": 5,
            "prerequisites": ["somatic_cell_count_udder_health"],
        },
        "content": (
            "Modern cooling techniques have shifted spoilage patterns in raw and pasteurized milk. Historically, milk "
            "spoiled by souring (lactose fermentation); however, today's flora is often dominated by psychrotrophic "
            "(cold-tolerant) bacteria, such as Pseudomonas. These organisms do not sour milk but rather produce enzymes "
            "that break down proteins and fats, leading to bitter, putrid, or unclean off-flavors even at refrigeration temperatures."
        ),
        "figure_alt": "Spoilage patterns and storage temperature",
        "figure_file": "l5f1.png",
        "key_points": [
            "Cooling milk to 6°C or lower is essential but favors different spoilage organisms than room-temperature storage.",
            "Small temperature changes have massive impacts: reducing the storage temperature by just 3°C can double the shelf life of pasteurized milk.",
        ],
        "question": "How has the widespread use of refrigeration changed the way milk typically spoils compared to the past?",
        "required_points": [
            "There is a shift from acid-producers causing souring to psychrotrophs that tolerate cold",
            "Spoilage now primarily involves enzymatic breakdown of fat and protein",
            "The result is bitter or unclean flavors rather than simple souring",
        ],
        "common_mistakes": [
            "Says refrigeration stops microbial spoilage completely",
            "Does not distinguish souring by acid producers from psychrotrophic enzymatic spoilage",
        ],
    },
]

for lesson in lessons:
    lesson_text = (
        f"{lesson['content']}\n\n"
        f"{figure_markdown(lesson['figure_alt'], lesson['figure_file'])}"
    )
    questions = [
        {
            "question_id": "q1",
            "question_text": lesson["question"],
            "answer_key": {
                "required_points": lesson["required_points"],
            },
            "rubric": {
                "max_score": len(lesson["required_points"]),
                "criteria": [
                    {"id": f"c{i}", "desc": point, "points": 1}
                    for i, point in enumerate(lesson["required_points"], start=1)
                ],
                "common_mistakes": lesson["common_mistakes"],
            },
        }
    ]

    add_topic_rows(
        rows,
        course_id=course_id,
        topic=lesson["topic"],
        lesson_text=lesson_text,
        key_points=lesson["key_points"],
        examples=[],
        questions=questions,
    )

DF_COURSE = pd.DataFrame(rows)
