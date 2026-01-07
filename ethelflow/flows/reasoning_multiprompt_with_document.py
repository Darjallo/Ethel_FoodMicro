import os
import uuid
from typing import Optional, TypedDict

from langgraph.graph import StateGraph

from ethelflow.agents.reasoning.node_adapter import reasoning_node

FLOW_NAME = os.path.splitext(os.path.basename(__file__))[0]


class ReasoningTestState(TypedDict, total=False):
    document_id: uuid.UUID
    content_type: str
    prompt_1: str
    prompt_2: str
    reasoning_effort: Optional[str]
    stream: bool
    response_1: str
    response_2: str


async def run(
    thread_id: uuid.UUID,
    context=None,
    stream=False,
    checkpointer=None,
    command=None,
):
    if not context or not isinstance(context, dict):
        raise ValueError("Missing or invalid context dictionary")

    prompt_1 = context.get("prompt_1")
    if not prompt_1:
        raise ValueError("Missing 'prompt_1' in context")

    prompt_2 = context.get("prompt_2")
    if not prompt_2:
        raise ValueError("Missing 'prompt_2' in context")

    content_type = context.get("content_type")
    if not content_type:
        raise ValueError("Missing 'content_type' in context")

    document_id = context.get("document_id")
    if not document_id:
        raise ValueError("Missing 'document_id' in context")

    reasoning_effort = context.get("reasoning_effort")

    initial_state: ReasoningTestState = {
        "document_id": uuid.UUID(str(document_id)),
        "content_type": content_type,
        "prompt_1": prompt_1,
        "prompt_2": prompt_2,
        "reasoning_effort": reasoning_effort,
        "stream": stream,
    }

    workflow = StateGraph(ReasoningTestState)

    workflow.add_node(
        "reasoning_1",
        reasoning_node(
            document_id_key="document_id",
            content_type_key="content_type",
            prompt_key="prompt_1",
            reasoning_effort_key="reasoning_effort",
            stream_key="stream",
            output_key="response_1",
        ),
    )

    @workflow.add_node
    def prepare_second_prompt(state: ReasoningTestState) -> ReasoningTestState:
        state["prompt_2"] = (state.get("response_1") or "") + f"\n\n\n{state['prompt_2']}"
        return state

    # Second call: no document attachment; just use the normal reasoning adapter.
    workflow.add_node(
        "reasoning_2",
        reasoning_node(
            prompt_key="prompt_2",
            reasoning_effort_key="reasoning_effort",
            stream_key="stream",
            output_key="response_2",
        ),
    )

    workflow.set_entry_point("reasoning_1")
    workflow.add_edge("reasoning_1", "prepare_second_prompt")
    workflow.add_edge("prepare_second_prompt", "reasoning_2")
    workflow.set_finish_point("reasoning_2")

    app = workflow.compile(checkpointer=checkpointer)
    config = {
        "metadata": {"flow": FLOW_NAME},
        "configurable": {"thread_id": str(thread_id)},
    }

    if stream:
        reasoning_1_done = False
        reasoning_2_done = False
        async for event in app.astream_events(initial_state, config=config, version="v2"):
            if (
                event.get("event") == "on_chain_stream"
                and "chunk" in event.get("data", {})
                and "response_1" in event["data"]["chunk"]
            ):
                chunk = event["data"]["chunk"]["response_1"]
                if reasoning_1_done or chunk is None:
                    reasoning_1_done = True
                    continue
                yield chunk

            if (
                event.get("event") == "on_chain_stream"
                and "chunk" in event.get("data", {})
                and "response_2" in event["data"]["chunk"]
            ):
                chunk = event["data"]["chunk"]["response_2"]
                if reasoning_2_done or chunk is None:
                    reasoning_2_done = True
                    continue
                yield chunk
    else:
        yield await app.ainvoke(initial_state, config=config)

