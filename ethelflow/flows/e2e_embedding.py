import uuid
from typing import List, Optional, TypedDict

from langgraph.graph import StateGraph

from ethelflow.agents.chunk_text.node_adapter import chunk_text_node
from ethelflow.agents.embedding.node_adapter import embedding_node
from ethelflow.agents.file_to_text.node_adapter import file_to_text_node
from ethelflow.agents.store_chunks.models import StoreChunksResponse
from ethelflow.agents.store_chunks.node_adapter import store_chunks_node
from ethelflow.agents.store_text.node_adapter import store_text_node
from ethelflow.agents.store_vectors.node_adapter import store_vectors_node


# End-to-end embedding flow for an Ethel document:
# 1. Extract text from file (document_id) with file_to_text agent
# 2. Store extracted text (document_texts) with store_text agent -> text_id
# 3. Chunk extracted text with chunk_text agent
# 4. Store chunks (chunksets/chunks) for text_id with store_chunks agent -> chunk_ids
# 5. Embed chunks with embedding agent
# 6. Store embeddings with store_vectors agent
class E2EEmbeddingState(TypedDict, total=False):
    document_id: uuid.UUID

    # file_to_text output
    text: str
    extractor: str  # required by store_text

    # store_text output
    text_id: str  # keep JSON-friendly (node_adapter returns str)
    store_text_response: dict

    # chunking
    chunks: List[str]
    method: str  # chunking method name

    # store_chunks output
    store_chunks_response: dict
    chunk_ids: List[uuid.UUID]

    # embeddings
    embeddings: List[List[float]]
    store_vectors_response: dict


def prepare_for_store_vectors(state: E2EEmbeddingState) -> E2EEmbeddingState:
    store_chunks_response = StoreChunksResponse.model_validate(state["store_chunks_response"])
    state["chunk_ids"] = store_chunks_response.chunk_ids
    return state


async def run(
    thread_id: uuid.UUID,
    context=None,
    stream: bool = False,
    checkpointer=None,
    command=None,
):
    context = context or {}
    initial_state: E2EEmbeddingState = {
        "document_id": context.get("document_id"),
        # store_text expects an extractor label; default is fine for now
        "extractor": context.get("extractor", "file_to_text"),
        "method": context.get("method", "recursive_char_1000_100_htmlstrip"),
    }

    workflow = StateGraph(E2EEmbeddingState)

    # Nodes
    file_to_text = file_to_text_node()
    store_text = store_text_node(
        document_id_key="document_id",
        extractor_key="extractor",
        text_key="text",
        output_text_id_key="text_id",
        output_key="store_text_response",
    )
    chunk_text = chunk_text_node(
        input_text_key="text",
        output_key="chunks",
        chunk_size=1000,
        chunk_overlap=100,
    )
    store_chunks = store_chunks_node(
        text_id_key="text_id",
        chunks_key="chunks",
        method_key="method",
        output_key="store_chunks_response",
    )
    embedding = embedding_node(input_texts_key="chunks", output_key="embeddings")
    store_vectors = store_vectors_node(embeddings_key="embeddings", chunk_ids_key="chunk_ids")

    # Graph
    workflow.add_node("file_to_text", file_to_text)
    workflow.add_node("store_text", store_text)
    workflow.add_node("chunk_text", chunk_text)
    workflow.add_node("store_chunks", store_chunks)
    workflow.add_node("embedding", embedding)
    workflow.add_node("prepare_for_store_vectors", prepare_for_store_vectors)
    workflow.add_node("store_vectors", store_vectors)

    workflow.set_entry_point("file_to_text")
    workflow.add_edge("file_to_text", "store_text")
    workflow.add_edge("store_text", "chunk_text")
    workflow.add_edge("chunk_text", "store_chunks")
    workflow.add_edge("store_chunks", "embedding")
    workflow.add_edge("embedding", "prepare_for_store_vectors")
    workflow.add_edge("prepare_for_store_vectors", "store_vectors")
    workflow.set_finish_point("store_vectors")

    app = workflow.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": str(thread_id)}}

    if stream:
        async for item in app.astream(initial_state, config=config):
            yield item
    else:
        yield await app.ainvoke(initial_state, config=config)

