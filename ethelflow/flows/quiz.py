import inspect
import logging
import os
import uuid
from typing import Optional, TypedDict

from langgraph.graph import StateGraph
from langgraph.pregel import Pregel
from langgraph.types import Command, interrupt

from ethelflow.agents.reasoning.node_adapter import reasoning_node

# Flow name to add to the metadata of each run
FLOW_NAME = os.path.splitext(os.path.basename(__file__))[0]

logger = logging.getLogger("uvicorn.error")


class QuizState(TypedDict, total=False):
    # routing / config
    tenant: str
    inference_class: str
    deployment: Optional[str]
    reasoning_effort: Optional[str]
    stream: bool

    # quiz content
    topic: str
    topic_prompt: str
    feedback_prompt: str
    question: str
    answer: str
    feedback: str


# ---- helper: only pass kwargs that reasoning_node actually accepts ----
_REASONING_NODE_PARAMS = set(inspect.signature(reasoning_node).parameters.keys())


def _reasoning_node(**kwargs):
    filtered = {k: v for k, v in kwargs.items() if k in _REASONING_NODE_PARAMS}
    return reasoning_node(**filtered)


async def run(
    thread_id: uuid.UUID,
    context=None,
    stream=False,
    command: Command = None,
    checkpointer=None,
):
    if command is not None and checkpointer is None:
        raise ValueError("Checkpointer must be provided when resuming a flow with a command")

    # If command is not provided, we are starting a new flow, so context must be provided
    if command is None:
        if not context or not isinstance(context, dict):
            raise ValueError("Missing or invalid context dictionary")

        topic = context.get("topic")
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError("Missing or invalid 'topic' in context")

        # IMPORTANT: tenant must be in context (flows currently only get `context`)
        tenant = context.get("tenant")
        if not isinstance(tenant, str) or not tenant.strip():
            raise ValueError("Missing or invalid 'tenant' in context")

        inference_class = context.get("inference_class", "reasoning")
        if not isinstance(inference_class, str) or not inference_class.strip():
            raise ValueError("Missing or invalid 'inference_class' in context")

        # Optional overrides
        deployment = context.get("deployment")
        reasoning_effort = context.get("reasoning_effort")

        initial_state: QuizState = {
            "topic": topic,
            "tenant": tenant,
            "inference_class": inference_class,
            "stream": bool(stream),
        }
        if deployment:
            initial_state["deployment"] = deployment
        if reasoning_effort:
            initial_state["reasoning_effort"] = reasoning_effort

    workflow = StateGraph(QuizState)

    @workflow.add_node
    def prepare_topic_prompt(state: QuizState) -> QuizState:
        state["topic_prompt"] = (
            "You are a quiz master. Prepare ONE challenging question about the following topic: "
            + state["topic"]
            + ".\n\n"
            + "First, provide a detailed explanation of the topic to help the user understand it better.\n\n"
            + "Then, create ONE question that test the user's understanding of the topic. "
            + "Make sure the questions are clear and unambiguous.\n\n"
            + "Format your response as follows:\n\n"
            + "Explanation: <detailed explanation>\n\n"
            + "Question: <first question>\n\n"
            + "Do not include any answers in your response."
        )
        return state

    workflow.add_node(
        "prepare_quiz",
        _reasoning_node(
            tenant_key="tenant",
            inference_class_key="inference_class",
            deployment_key="deployment",
            prompt_key="topic_prompt",
            reasoning_effort_key="reasoning_effort",
            stream_key="stream",
            output_key="question",
        ),
    )

    @workflow.add_node
    def human_answer(state: QuizState) -> QuizState:
        state["answer"] = interrupt(state["question"])
        return state

    @workflow.add_node
    def prepare_feedback_prompt(state: QuizState) -> QuizState:
        state["feedback_prompt"] = (
            "You are a quiz master. Here is the question you asked:\n\n"
            + state["question"]
            + "\n\n"
            + "The user answered:\n\n"
            + state["answer"]
            + "\n\n"
            + "First, provide the correct answer to the question.\n\n"
            + "Then, evaluate the user's answer and provide feedback on its correctness and completeness.\n\n"
            + "Format your response as follows:\n\n"
            + "Correct Answer: <correct answer>\n\n"
            + "Feedback: <detailed feedback>\n\n"
            + "Make sure to be constructive and encouraging in your feedback."
        )
        return state

    workflow.add_node(
        "feedback",
        _reasoning_node(
            tenant_key="tenant",
            inference_class_key="inference_class",
            deployment_key="deployment",
            prompt_key="feedback_prompt",
            reasoning_effort_key="reasoning_effort",
            stream_key="stream",
            output_key="feedback",
        ),
    )

    workflow.set_entry_point("prepare_topic_prompt")
    workflow.add_edge("prepare_topic_prompt", "prepare_quiz")
    workflow.add_edge("prepare_quiz", "human_answer")
    workflow.add_edge("human_answer", "prepare_feedback_prompt")
    workflow.add_edge("prepare_feedback_prompt", "feedback")
    workflow.set_finish_point("feedback")

    # Compile the graph
    app: Pregel = workflow.compile(checkpointer=checkpointer)
    config = {
        "metadata": {"flow": FLOW_NAME},
        "configurable": {"thread_id": str(thread_id)},
    }

    # If we are resuming the flow with a command, we use the command as the input.
    # Otherwise, we start with the initial state.
    input: QuizState | Command = command if command is not None else initial_state

    if command is not None:
        logger.info(f"Resuming flow {FLOW_NAME} for run_id: {thread_id}, with command: {command}")

    if stream:
        async for event in app.astream_events(input, config=config, version="v2"):
            yield str(event)
    else:
        yield await app.ainvoke(input, config=config)

