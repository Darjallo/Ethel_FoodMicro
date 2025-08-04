from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from ethelflow.agents.chunk_text.node_adapter import chunk_text_node
from ethelflow.agents.embedding.node_adapter import embedding_node


class ChunkAndEmbedState(TypedDict):
    text: str
    texts: list[str]
    embeddings: dict


async def run(context=None, stream=False, query=None, file_id=None):
    state: ChunkAndEmbedState = {"text": context.get("text")}
    flow = StateGraph(ChunkAndEmbedState)

    chunking_node = chunk_text_node(input_text_key="text", output_key="texts")
    embed_node = embedding_node(input_texts_key="texts", output_key="embeddings")

    flow.add_node("chunk", chunking_node)
    flow.add_node("embed", embed_node)
    flow.add_edge(START, "chunk")
    flow.add_edge("chunk", "embed")
    flow.add_edge("embed", END)
    app = flow.compile()

    if stream:
        async for item in app.astream(state):
            yield item
    else:
        yield await app.ainvoke(state)
