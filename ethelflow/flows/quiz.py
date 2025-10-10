from typing import TypedDict
import uuid
import os
import logging
from langgraph.graph import StateGraph
from langgraph.pregel import Pregel
from langgraph.types import interrupt, Command
from ethelflow.agents.reasoning.node_adapter import reasoning_node


# Flow name to add to the metadata of each run
FLOW_NAME = os.path.splitext(os.path.basename(__file__))[0]

logger = logging.getLogger("uvicorn.error")


class QuizState(TypedDict, total=False):
    topic: str
    deployment: str
    topic_prompt: str
    feedback_prompt: str
    question: str
    answer: str
    feedback: str


async def run(
    thread_id: uuid.UUID,
    context=None,
    stream=False,
    command: Command = None,
    checkpointer=None,
):
    if command is not None and checkpointer is None:
        raise ValueError(
            "Checkpointer must be provided when resuming a flow with a command"
        )
    # If command is not provided, we are starting a new flow, so context must be provided
    if command is None:
        if not context or not isinstance(context, dict):
            raise ValueError("Missing or invalid context dictionary")

        topic = context.get("topic")
        if not isinstance(topic, str):
            raise ValueError("Missing or invalid 'topic' in context")

        initial_state: QuizState = {"topic": topic, "deployment": "Ethel_o4_mini"}

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
        reasoning_node(
            prompt_key="topic_prompt",
            reasoning_effort_key=None,
            stream_key=None,
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
        reasoning_node(
            prompt_key="feedback_prompt",
            reasoning_effort_key=None,
            stream_key=None,
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

    # If we are resuming the flow with a command (because an interrupt has been handled by the user),
    # we use the command as the input to the flow. Otherwise, we start with the initial state.
    input: QuizState | Command = command if command is not None else initial_state

    if command is not None:
        logger.info(
            f"Resuming flow {FLOW_NAME} for run_id: {thread_id}, with command: {command}"
        )
    if stream:
        async for event in app.astream_events(input, config=config, version="v2"):
            yield str(event)

    else:
        yield await app.ainvoke(input, config=config)
