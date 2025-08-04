# Project Ethel
# Node adapter for semantically chunking text
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
from typing import Callable, Dict, Any, AsyncGenerator
from ethelflow.agents.embedding.models import EmbeddingRequest, EmbeddingResponse
import aiohttp

# could also be an environment variable
EMBEDDING_URL: str = "http://embedding.default.svc:8000/embedding"


def embedding_node(
    input_texts_key: str = "texts",
    output_key: str = "embeddings",
) -> Callable[[Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
    async def node(state: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        # 1) Fetch raw text from state
        input_texts = state.get(input_texts_key)
        if not isinstance(input_texts, list) or not all(
            isinstance(text, str) for text in input_texts
        ):
            raise ValueError(
                f"Expected list of strings for {input_texts_key}, got {type(input_texts)}"
            )

        # 2) Build payload and POST to the running chunk_text agent
        request = EmbeddingRequest(
            texts=input_texts,
            deployment="EthelEmb3large",
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(
                EMBEDDING_URL, json=request.model_dump(), timeout=60
            ) as response:
                if response.status != 200:
                    raise ValueError(
                        f"Embedding service returned status {response.status}"
                    )
                response_data = await response.json()

                data = EmbeddingResponse.model_validate(response_data)

        yield {output_key: data}

    return node
