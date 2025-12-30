from typing import Callable, Dict, Any, AsyncGenerator
import aiohttp
import uuid

from ethelflow.agents.store_chunks.models import StoreChunksRequest, StoreChunksResponse

# could also be an environment variable
STORE_CHUNKS_URL: str = "http://store-chunks.default.svc:8000/store_chunks"


def _as_uuid(val: Any, field_name: str) -> uuid.UUID:
    if isinstance(val, uuid.UUID):
        return val
    if val is None:
        raise ValueError(f"{field_name} is required")
    try:
        return uuid.UUID(str(val))
    except Exception as e:
        raise ValueError(f"Invalid UUID format for {field_name}: {val!r}") from e


def store_chunks_node(
    text_id_key: str = "text_id",
    chunks_key: str = "chunks",
    method_key: str = "method",
    output_key: str = "store_chunks_response",
    replace_key: str = "replace",  # optional in state
) -> Callable[[Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
    async def node(state: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        text_id = _as_uuid(state.get(text_id_key), text_id_key)

        chunks = state.get(chunks_key)
        if not isinstance(chunks, list) or not all(isinstance(c, str) for c in chunks):
            raise ValueError(f"Expected list[str] for {chunks_key}, got {type(chunks)}")

        method = state.get(method_key)
        if not isinstance(method, str):
            raise ValueError(f"Expected str for {method_key}, got {type(method)}")

        replace = state.get(replace_key, True)
        if not isinstance(replace, bool):
            replace = str(replace).lower() in ("1", "true", "yes")

        request = StoreChunksRequest(
            text_id=text_id,
            chunks=chunks,
            method=method,
            replace=replace,
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(
                STORE_CHUNKS_URL,
                json=request.model_dump(mode="json"),
                timeout=60,
            ) as resp:
                if resp.status != 200:
                    raise ValueError(f"Store chunks service returned status {resp.status}")
                payload = await resp.json()

        data = StoreChunksResponse.model_validate(payload)
        # keep state JSON-friendly
        yield {output_key: data.model_dump(mode="json")}

    return node

