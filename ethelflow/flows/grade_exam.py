import os
import operator
import uuid
from typing import Annotated, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ethelflow.agents.pdf_to_images.node_adapter import pdf_to_images_node
from ethelflow.agents.reasoning.node_adapter import reasoning_node

FLOW_NAME = os.path.splitext(os.path.basename(__file__))[0]


class GradeExamState(TypedDict, total=False):
    exam_document_id: uuid.UUID
    rubric_document_id: uuid.UUID
    deployment: str
    reasoning_effort: Optional[str]
    dpi: int
    prompt: str
    stream: bool
    exam_pages: list[dict]
    rubric_pages: list[dict]
    results: Annotated[list[dict], operator.add]
    latest_result: Annotated[list[dict], operator.add]
    page_number: int
    rubric_document_id: uuid.UUID
    images: list[dict]


async def _run_single(node, state):
    gen = node(state)
    return await anext(gen)


async def run(
    thread_id: uuid.UUID,
    context=None,
    stream=False,
    checkpointer=None,
    command=None,
):
    if not context or not isinstance(context, dict):
        raise ValueError("Missing or invalid context dictionary")

    exam_document_id = context.get("exam_document_id")
    rubric_document_id = context.get("rubric_document_id")
    deployment = context.get("deployment")
    reasoning_effort = context.get("reasoning_effort")
    dpi = context.get("dpi", 300)
    prompt = context.get("prompt")

    if not exam_document_id:
        raise ValueError("Missing 'exam_document_id' in context")
    if not rubric_document_id:
        raise ValueError("Missing 'rubric_document_id' in context")
    if not deployment:
        raise ValueError("Missing 'deployment' in context")

    workflow = StateGraph(GradeExamState)

    workflow.add_node(
        "split_exam",
        pdf_to_images_node(
            document_id_key="exam_document_id",
            dpi_key="dpi",
            output_key="exam_pages",
        ),
    )
    workflow.add_node(
        "split_rubric",
        pdf_to_images_node(
            document_id_key="rubric_document_id",
            dpi_key="dpi",
            output_key="rubric_pages",
        ),
    )

    grade_node = reasoning_node(
        images_key="images",
        prompt_key="prompt",
        reasoning_effort_key="reasoning_effort",
        stream_key="stream",
        output_key="grading",
    )

    def dispatch_grading(state: GradeExamState):
        exam_pages = sorted(state["exam_pages"], key=lambda p: p["page_number"])
        rubric_pages = sorted(state["rubric_pages"], key=lambda p: p["page_number"])

        if len(exam_pages) != len(rubric_pages):
            raise ValueError(
                f"Page count mismatch: exam has {len(exam_pages)}, rubric has {len(rubric_pages)}"
            )

        rubric_by_page = {page["page_number"]: page for page in rubric_pages}

        sends: list[Send] = []
        for exam_page in exam_pages:
            page_number = exam_page["page_number"]
            rubric_page = rubric_by_page.get(page_number)
            if rubric_page is None:
                raise ValueError(f"Missing rubric page {page_number}")

            sends.append(
                Send(
                    "grade_page",
                    {
                        "page_number": page_number,
                        "images": [
                            {
                                "content_type": exam_page.get(
                                    "content_type", "image/png"
                                ),
                                "data_base64": exam_page["data_base64"],
                            },
                            {
                                "content_type": rubric_page.get(
                                    "content_type", "image/png"
                                ),
                                "data_base64": rubric_page["data_base64"],
                            },
                        ],
                        "deployment": state["deployment"],
                        "reasoning_effort": state.get("reasoning_effort"),
                        "prompt": state.get("prompt")
                        or "Please grade this student page using the rubric image below.",
                        "stream": False,
                    },
                )
            )

        return sends

    @workflow.add_node
    async def grade_page(state: GradeExamState):
        grade_result = await _run_single(
            grade_node,
            {
                "images": state["images"],
                "deployment": state["deployment"],
                "reasoning_effort": state.get("reasoning_effort"),
                "stream": False,
                "prompt": state.get("prompt"),
            },
        )

        page_result = {
            "page_number": state["page_number"],
            "grading": grade_result["grading"],
        }

        return {"latest_result": [page_result], "results": [page_result]}

    workflow.add_edge(START, "split_exam")
    workflow.add_edge("split_exam", "split_rubric")
    workflow.add_conditional_edges("split_rubric", dispatch_grading, ["grade_page"])
    workflow.add_edge("grade_page", END)

    app = workflow.compile(checkpointer=checkpointer)
    config = {
        "metadata": {"flow": FLOW_NAME},
        "configurable": {"thread_id": str(thread_id)},
    }

    initial_state: GradeExamState = {
        "exam_document_id": uuid.UUID(exam_document_id),
        "rubric_document_id": uuid.UUID(rubric_document_id),
        "deployment": deployment,
        "reasoning_effort": reasoning_effort,
        "dpi": dpi,
        "prompt": prompt,
        "stream": stream,
        "results": [],
    }

    if stream:
        async for event in app.astream_events(
            initial_state, config=config, version="v2"
        ):
            if (
                event["event"] == "on_chain_stream"
                and "chunk" in event["data"]
                and "latest_result" in event["data"]["chunk"]
            ):
                latest = event["data"]["chunk"]["latest_result"]
                if not latest:
                    continue
                for item in latest:
                    yield str(item)
    else:
        result = await app.ainvoke(initial_state, config=config)
        results = result.get("results", [])
        results.sort(key=lambda item: item.get("page_number", 0))
        yield results
