from typing import TypedDict, Optional
import uuid
from langgraph.graph import StateGraph
from ethelflow.agents.reasoning.node_adapter import reasoning_node


class ReasoningTestState(TypedDict, total=False):
    deployment: str
    document_id: uuid.UUID
    content_type: str
    prompt: str
    reasoning_effort: Optional[str]
    stream: bool
    reasoning_response: str


async def run(
    thread_id: uuid.UUID,
    context=None,
    stream=False,
    checkpointer=None,
    command=None,
):
    """
    Runs a test of the reasoning agent.
    """
    if not context or not isinstance(context, dict):
        raise ValueError("Missing or invalid context dictionary")

    prompt = context.get("prompt")
    if not prompt:
        raise ValueError("Missing 'prompt' in context")

    content_type = context.get("content_type")
    if not content_type:
        raise ValueError("Missing 'content_type' in context")

    document_id = context.get("document_id")
    if not document_id:
        raise ValueError("Missing 'document_id' in context")

    deployment = context.get("deployment")
    if not deployment:
        raise ValueError("Missing 'deployment' in context")

    reasoning_effort = context.get("reasoning_effort")

    initial_state: ReasoningTestState = {
        "deployment": deployment,
        "document_id": uuid.UUID(document_id),
        "content_type": content_type,
        "prompt": prompt,
        "reasoning_effort": reasoning_effort,
        "stream": stream,
    }

    workflow = StateGraph(ReasoningTestState)

    workflow.add_node(
        "reasoning",
        reasoning_node(
            document_id_key="document_id",
            content_type_key="content_type",
            prompt_key="prompt",
            reasoning_effort_key="reasoning_effort",
            stream_key="stream",
            output_key="reasoning_response",
        ),
    )

    workflow.set_entry_point("reasoning")
    workflow.set_finish_point("reasoning")

    app = workflow.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": str(thread_id)}}

    if stream:
        async for item in app.astream_events(initial_state, config, version="v2"):
            if item["event"] == "on_chain_stream":
                chunk = item["data"]["chunk"]
                if (
                    isinstance(chunk, dict)
                    and "reasoning_response" in chunk
                    and chunk["reasoning_response"] is not None
                ):
                    yield chunk["reasoning_response"]
    else:
        yield await app.ainvoke(initial_state, config)
