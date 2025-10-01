from typing import TypedDict, Optional
import uuid
from langgraph.graph import StateGraph
from ethelflow.agents.reasoning.node_adapter import reasoning_node


class ReasoningTestState(TypedDict, total=False):
    deployment: str
    prompt_1: str
    prompt_2: str
    reasoning_effort: Optional[str]
    stream: bool
    response_1: str
    response_2: str


async def run(
    thread_id: uuid.UUID,
    context=None,
    query=None,
    file_id=None,
    stream=False,
    checkpointer=None,
):
    """
    Runs a test of the reasoning agent.
    """
    if not context or not isinstance(context, dict):
        raise ValueError("Missing or invalid context dictionary")

    prompt_1 = context.get("prompt_1")
    if not prompt_1:
        raise ValueError("Missing 'prompt_1' in context")

    prompt_2 = context.get("prompt_2")
    if not prompt_2:
        raise ValueError("Missing 'prompt_2' in context")

    deployment = context.get("deployment")
    if not deployment:
        raise ValueError("Missing 'deployment' in context")

    reasoning_effort = context.get("reasoning_effort")

    initial_state: ReasoningTestState = {
        "deployment": deployment,
        "prompt_1": prompt_1,
        "prompt_2": prompt_2,
        "reasoning_effort": reasoning_effort,
        "stream": stream,
    }

    workflow = StateGraph(ReasoningTestState)

    workflow.add_node(
        "reasoning_1",
        reasoning_node(
            prompt_key="prompt_1",
            reasoning_effort_key="reasoning_effort",
            stream_key="stream",
            output_key="response_1",
        ),
    )

    @workflow.add_node
    def prepare_second_prompt(state: ReasoningTestState) -> ReasoningTestState:
        state["prompt_2"] = state["response_1"] + f"\n\n\n{state['prompt_2']}"
        return state

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

    # Compile the graph
    app = workflow.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": str(thread_id)}}

    if stream:
        # We need some logic here to not return the same response twice, since the response
        # is first streamed chunk by chunk, and then once more as the full response at the end.
        # The node adapter returns None between the last chunk and the final full response, this signals
        # the end of the chunk stream, so we can skip it.
        reasoning_1_done = False
        reasoning_2_done = False
        async for event in app.astream_events(
            initial_state, config=config, version="v2"
        ):
            if (
                event["event"] == "on_chain_stream"
                and "chunk" in event["data"]
                and "response_1" in event["data"]["chunk"]
            ):
                if reasoning_1_done or event["data"]["chunk"]["response_1"] is None:
                    reasoning_1_done = True
                    continue
                yield event["data"]["chunk"]["response_1"]
            if (
                event["event"] == "on_chain_stream"
                and "chunk" in event["data"]
                and "response_2" in event["data"]["chunk"]
            ):
                if reasoning_2_done or event["data"]["chunk"]["response_2"] is None:
                    reasoning_2_done = True
                    continue
                yield event["data"]["chunk"]["response_2"]
    else:
        yield await app.ainvoke(initial_state, config=config)
