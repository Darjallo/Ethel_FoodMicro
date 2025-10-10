from typing import Callable, Dict, Any, AsyncGenerator
from ethelflow.agents.store_chunks.models import (
    StoreChunksRequest,
    StoreChunksResponse,
)
import aiohttp
import uuid

# could also be an environment variable
STORE_CHUNKS_URL: str = "http://store-chunks.default.svc:8000/store_chunks"


def store_chunks_node(
    document_id_key: str = "document_id",
    chunks_key: str = "chunks",
    method_key: str = "method",
    output_key: str = "store_chunks_response",
) -> Callable[[Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
    async def node(state: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        # 1) Fetch data from state
        try:
            document_id = uuid.UUID((state.get(document_id_key)))
        except ValueError as e:
            raise ValueError(
                f"Invalid UUID format for {document_id_key}: {state.get(document_id_key)}"
            ) from e

        chunks = state.get(chunks_key)
        if not isinstance(chunks, list) or not all(
            isinstance(chunk, str) for chunk in chunks
        ):
            raise ValueError(
                f"Expected list of strings for {chunks_key}, got {type(chunks)}"
            )

        method = state.get(method_key)
        if not isinstance(method, str):
            raise ValueError(f"Expected string for {method_key}, got {type(method)}")

        # 2) Build payload and POST to the running store_chunks agent
        request = StoreChunksRequest(
            document_id=document_id,
            chunks=chunks,
            method=method,
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(
                STORE_CHUNKS_URL, json=request.model_dump(mode="json"), timeout=60
            ) as response:
                if response.status != 200:
                    raise ValueError(
                        f"Store chunks service returned status {response.status}"
                    )
                response_data = await response.json()

                data = StoreChunksResponse.model_validate(response_data)

        yield {output_key: data}

    return node
