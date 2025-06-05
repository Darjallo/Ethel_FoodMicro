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

    # Output of the second node (single embedding vector)
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

    # 2) Build the batch‐embedding factory:
    #    It now expects a list of strings under state["texts"]
    batch_emb_fn = emb_ada3large_node(
        input_text_key="texts",                 # read state["texts"] (a list[str])
        output_key="emb_ada3large_batch"        # write state["emb_ada3large_batch"] (list of vectors)
    )

    # 3) Wrap around batch_emb_fn to extract exactly one string from test_agent_result,
    #    call batch_emb_fn with {"texts": [that_string]}, then unwrap the first vector.
    def emb_wrapper_node(state_dict: dict):
        """
        1) Pull the raw OpenAI‐style dict from state["test_agent_result"].
        2) Extract choices[0]["message"]["content"] as a string.
        3) Call batch_emb_fn with {"texts": [assistant_text]}.
        4) From the returned { "emb_ada3large_batch": [ [vec] ] }, extract vec → yield
           { "emb_ada3large_result": vec }.
        """
        raw = state_dict.get("test_agent_result", {}) or {}
        assistant_text = ""
        try:
            choices = raw.get("choices", [])
            if isinstance(choices, list) and len(choices) > 0:
                msg = choices[0].get("message", {})
                assistant_text = msg.get("content", "") or ""
        except Exception:
            assistant_text = ""

        # Wrap into a one‐element list for batch embedding
        batch_input = {"texts": [assistant_text]}

        # batch_emb_fn returns an iterator that yields a dict like:
        #   {"emb_ada3large_batch": [ [float, float, …], … ]}
        for output in batch_emb_fn(batch_input):
            batch_list = output.get("emb_ada3large_batch", [])
            # take the first vector (since we only passed one input)
            single_vec: list[float] = []
            if isinstance(batch_list, list) and len(batch_list) > 0:
                first_item = batch_list[0]
                if isinstance(first_item, list):
                    single_vec = first_item
            # yield in the old format (single vector under "emb_ada3large_result")
            yield {"emb_ada3large_result": single_vec}

    # 4) Register nodes:
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

