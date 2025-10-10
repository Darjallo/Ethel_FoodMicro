# Project Ethel
# Node adapter for storing vectors
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
from ethelflow.agents.store_vectors.models import (
    StoreVectorsRequest,
    StoreVectorsResponse,
)
import aiohttp
import uuid

# could also be an environment variable
STORE_VECTORS_URL: str = "http://store-vectors.default.svc:8000/store_vectors"


def store_vectors_node(
    embeddings_key: str = "embeddings",
    chunk_ids_key: str = "chunk_ids",
    output_key: str = "store_vectors_response",
) -> Callable[[Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
    async def node(state: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        # 1) Fetch data from state
        embeddings = state.get(embeddings_key)
        if not isinstance(embeddings, list) or not all(
            isinstance(embedding, list) for embedding in embeddings
        ):
            raise ValueError(
                f"Expected list of lists of floats for {embeddings_key}, got {type(embeddings)}"
            )

        chunk_ids = state.get(chunk_ids_key)
        if not isinstance(chunk_ids, list) or not all(
            isinstance(chunk_id, uuid.UUID) for chunk_id in chunk_ids
        ):
            raise ValueError(
                f"Expected list of UUIDs for {chunk_ids_key}, got {type(chunk_ids)}"
            )

        # 2) Build payload and POST to the running store_vectors agent
        request = StoreVectorsRequest(
            embeddings=embeddings,
            chunk_ids=chunk_ids,
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(
                STORE_VECTORS_URL, json=request.model_dump(mode="json"), timeout=60
            ) as response:
                if response.status != 200:
                    raise ValueError(
                        f"Store vectors service returned status {response.status}"
                    )
                response_data = await response.json()

                data = StoreVectorsResponse.model_validate(response_data)

        yield {output_key: data}

    return node
