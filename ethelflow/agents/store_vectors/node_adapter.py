from __future__ import annotations

from typing import Any, AsyncGenerator, Callable, Dict, Optional
import aiohttp
import uuid

from ethelflow.agents.store_vectors.models import StoreVectorsRequest, StoreVectorsResponse

STORE_VECTORS_URL: str = "http://store-vectors.default.svc:8000/store_vectors"


def store_vectors_node(
    embeddings_key: str = "embeddings",
    chunk_ids_key: str = "chunk_ids",
    tenant_key: str = "tenant",
    space_key: str = "embedding_space",  # optional
    output_key: str = "store_vectors_response",
) -> Callable[[Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
    async def node(state: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        embeddings = state.get(embeddings_key)
        if not isinstance(embeddings, list) or not all(isinstance(v, list) for v in embeddings):
            raise ValueError(f"Expected list[list[float]] for {embeddings_key}, got {type(embeddings)}")

        chunk_ids = state.get(chunk_ids_key)
        if not isinstance(chunk_ids, list) or not all(isinstance(cid, uuid.UUID) for cid in chunk_ids):
            raise ValueError(f"Expected list[UUID] for {chunk_ids_key}, got {type(chunk_ids)}")

        tenant = state.get(tenant_key)
        if not isinstance(tenant, str) or not tenant.strip():
            raise ValueError(f"Expected non-empty str for {tenant_key}, got {tenant!r}")

        space: Optional[str] = state.get(space_key)
        if space is not None and (not isinstance(space, str) or not space.strip()):
            raise ValueError(f"Expected str|None for {space_key}, got {space!r}")

        req = StoreVectorsRequest(
            embeddings=embeddings,
            chunk_ids=chunk_ids,
            tenant=tenant,
            space=space,
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(STORE_VECTORS_URL, json=req.model_dump(mode="json"), timeout=300) as resp:
                if resp.status != 200:
                    raise ValueError(f"Store vectors service returned status {resp.status}: {await resp.text()}")
                payload = await resp.json()

        data = StoreVectorsResponse.model_validate(payload)
        yield {output_key: data.model_dump(mode="json")}

    return node

