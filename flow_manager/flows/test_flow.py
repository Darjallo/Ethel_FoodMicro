# Project Ethel
# A test flow, can serve as template
#
# Copyright (C) 2025  Gerd Kortemeyer, ETH Zurich
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# flow_manager/flows/test_flow.py

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .nodes import test_agent_node, emb_ada3large_node

class TestFlowState(TypedDict, total=False):
    # Inputs from the user
    context: dict
    query: dict
    stream: bool

    # Output of the first node (“test_agent”), which is an OpenAI‐style dict
    test_agent_result: dict

    # Output of the second node (embedding vector)
    emb_ada3large_result: list[float]


def run(context=None, query=None, file_id=None, stream=False):
    """
    Entry point for test_flow.
    Yields one dict per node when stream=True,
    otherwise yields just the final dict.
    """
    # Initialize shared state:
    state = {
        "context": context,
        "query": query or {},
        "stream": stream
    }

    builder = StateGraph(TestFlowState)

    # 1) First node: test_agent_node → returns a dict under "test_agent_result"
    test_agent_fn = test_agent_node(
        input_key_map={"context": "context", "query": "query"},
        output_key="test_agent_result"
    )

    # 2) Build the base embedding‐factory (it expects state["text"] to be a string)
    base_emb_fn = emb_ada3large_node(
        input_text_key="text",                # it will look in state["text"]
        output_key="emb_ada3large_result"
    )

    # 3) Wrap around base_emb_fn to extract the string from test_agent_result:
    def emb_wrapper_node(state_dict: dict):
        """
        1) Pull the raw OpenAI‐style dict from state["test_agent_result"].
        2) Extract choices[0]["message"]["content"].
        3) Call base_emb_fn with a new small dict {"text": that_string}.
        4) Yield exactly the { "emb_ada3large_result": vector } that base_emb_fn yields.
        """
        raw = state_dict.get("test_agent_result", {})
        assistant_text = ""
        try:
            # Traverse to choices[0]["message"]["content"]
            choices = raw.get("choices", [])
            if isinstance(choices, list) and len(choices) > 0:
                msg = choices[0].get("message", {})
                assistant_text = msg.get("content", "") or ""
        except Exception:
            assistant_text = ""

        # Now call the embedding factory as if we had state={"text": assistant_text}
        # base_emb_fn returns an iterator; we “yield from” it to pass through {emb_…: vector}
        yield from base_emb_fn({"text": assistant_text})

    # 4) Register nodes in the graph:
    builder.add_node("call_test_agent", test_agent_fn)
    builder.add_node("call_embedding", emb_wrapper_node)

    # 5) Wire up execution: START → call_test_agent → call_embedding → END
    builder.add_edge(START, "call_test_agent")
    builder.add_edge("call_test_agent", "call_embedding")
    builder.add_edge("call_embedding", END)

    app = builder.compile()

    # 6) Run or stream:
    if stream:
        iterator = app.stream(state)
    else:
        iterator = iter([app.invoke(state)])

    for update in iterator:
        yield update

