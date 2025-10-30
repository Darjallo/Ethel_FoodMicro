import logging
import os
import uuid
from typing import TypedDict

from langgraph.graph import StateGraph
from langgraph.pregel import Pregel
from langgraph.types import Command
from sqlmodel import Session, create_engine

from ethelflow.agents.embedding.node_adapter import embedding_node
from ethelflow.agents.reasoning.node_adapter import reasoning_node
from ethelflow.settings.postgres_settings import postgres_settings

engine = create_engine(postgres_settings.url)


def get_session():
    with Session(engine) as session:
        yield session


# Flow name to add to the metadata of each run
FLOW_NAME = os.path.splitext(os.path.basename(__file__))[0]

logger = logging.getLogger("uvicorn.error")


class QAState(TypedDict, total=False):
    question: list[str]
    deployment: str
    question_embeddings: list[list[float]]
    prompt: str
    answer: str
    method: str
    top_k: int
    threshold: float
    stream: bool


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

        question = context.get("question")
        top_k = context.get("top_k", 10)
        threshold = context.get("threshold", 0.4)
        method = context.get("method", "recursive_char_500_50")
        if not isinstance(question, str):
            raise ValueError("Missing or invalid 'question' in context")

        initial_state: QAState = {
            "deployment": "Ethel_5",
            "question": [question],
            "top_k": top_k,
            "stream": stream,
        }

    workflow = StateGraph(QAState)

    # Step 1: get the embeddings for the question
    workflow.add_node(
        "embed_question",
        embedding_node(input_texts_key="question", output_key="question_embeddings"),
    )

    # Step 2: use the embeddings to search for relevant documents
    @workflow.add_node
    async def retrieve_documents(state: QAState) -> QAState:
        from ethelflow.data.vectors import get_relevant_chunks

        question_embeddings = state["question_embeddings"]
        if not question_embeddings:
            raise ValueError("No question embeddings found in state")

        embedding = question_embeddings[0]

        # XXX: should use an async session, probably a global one
        with Session(engine) as session:
            chunks = get_relevant_chunks(
                session=session,
                query_vector=embedding,
                top_k=top_k,
                distance_threshold=threshold,
                method=method,
            )

        # Construct the prompt with the retrieved chunks
        prompt = """
        You are an helpful assistant tasked with answering user's questions based on the provided document excerpts.
        Provide an accurate and extensive answer to the questions asked by the users. Explain open-ended questions in detail.
        The excerpts are provided from a set of news articles from ETH Zürich, an university located in Switzerland. The excepts
        may be in German or English.
        Use the following context to answer the question:\n\n
        """
        for chunk in chunks:
            prompt += chunk["text"] + "\n\n"
        prompt += "Question: " + state["question"][0]

        state["prompt"] = prompt
        return state

    # Step 3: use the reasoning agent to answer the question based on the retrieved documents
    workflow.add_node(
        "answer_question",
        reasoning_node(
            prompt_key="prompt",
            reasoning_effort_key=None,
            stream_key="stream",
            output_key="answer",
        ),
    )

    workflow.set_entry_point("embed_question")
    workflow.add_edge("embed_question", "retrieve_documents")
    workflow.add_edge("retrieve_documents", "answer_question")
    workflow.set_finish_point("answer_question")

    # Compile the graph
    app: Pregel = workflow.compile(checkpointer=checkpointer)
    config = {
        "metadata": {"flow": FLOW_NAME},
        "configurable": {"thread_id": str(thread_id)},
    }

    # If we are resuming the flow with a command (because an interrupt has been handled by the user),
    # we use the command as the input to the flow. Otherwise, we start with the initial state.
    input: QAState | Command = command if command is not None else initial_state

    if command is not None:
        logger.info(
            f"Resuming flow {FLOW_NAME} for run_id: {thread_id}, with command: {command}"
        )
    if stream:
        reasoning_done = False
        async for event in app.astream_events(input, config=config, version="v2"):
            if (
                event["event"] == "on_chain_stream"
                and "chunk" in event["data"]
                and "answer" in event["data"]["chunk"]
            ):
                if reasoning_done or event["data"]["chunk"]["answer"] is None:
                    reasoning_done = True
                    continue
                yield event["data"]["chunk"]["answer"]
        # async for event in app.astream_events(input, config=config, version="v2"):
        #     yield str(event)

    else:
        yield await app.ainvoke(input, config=config)
