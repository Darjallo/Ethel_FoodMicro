from __future__ import annotations

from typing import Any, AsyncGenerator, Callable, Dict, Optional, List
import aiohttp
import uuid

from ethelflow.agents.search_vectors.models import SearchVectorsRequest, SearchVectorsResponse

SEARCH_VECTORS_URL: str = "http://search-vectors.default.svc:8000/search_vectors"


def _as_uuid(val: Any, field_name: str) -> uuid.UUID:
    if isinstance(val, uuid.UUID):
        return val
    if val is None:
        raise ValueError(f"{field_name} is required")
    try:
        return uuid.UUID(str(val))
    except Exception as e:
        raise ValueError(f"Invalid UUID format for {field_name}: {val!r}") from e


def search_vectors_node(
    document_ids_key: str = "document_ids",
    extractor_key: str = "extractor",
    method_key: str = "method",
    tenant_key: str = "tenant",
    space_key: str = "embedding_space",      # optional
    query_embedding_key: str = "query_embedding",
    top_k_key: str = "top_k",
    output_key: str = "search_vectors_response",
    output_chunk_ids_key: str = "hit_chunk_ids",
) -> Callable[[Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
    async def node(state: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        raw_doc_ids = state.get(document_ids_key)
        if not isinstance(raw_doc_ids, list) or not raw_doc_ids:
            raise ValueError(f"Expected non-empty list for {document_ids_key}")

        document_ids: List[uuid.UUID] = [_as_uuid(x, f"{document_ids_key}[{i}]") for i, x in enumerate(raw_doc_ids)]

        extractor = state.get(extractor_key)
        if not isinstance(extractor, str) or not extractor.strip():
            raise ValueError(f"Expected non-empty str for {extractor_key}, got {extractor!r}")

        method = state.get(method_key)
        if not isinstance(method, str) or not method.strip():
            raise ValueError(f"Expected non-empty str for {method_key}, got {method!r}")

        tenant = state.get(tenant_key)
        if not isinstance(tenant, str) or not tenant.strip():
            raise ValueError(f"Expected non-empty str for {tenant_key}, got {tenant!r}")

        space: Optional[str] = state.get(space_key)
        if space is not None and (not isinstance(space, str) or not space.strip()):
            raise ValueError(f"Expected str|None for {space_key}, got {space!r}")

        query_embedding = state.get(query_embedding_key)
        if not isinstance(query_embedding, list) or not all(isinstance(x, (int, float)) for x in query_embedding):
            raise ValueError(f"Expected list[float] for {query_embedding_key}")

        top_k = state.get(top_k_key, 10)
        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError(f"Expected positive int for {top_k_key}, got {top_k!r}")

        req = SearchVectorsRequest(
            document_ids=document_ids,
            extractor=extractor,
            method=method,
            tenant=tenant,
            space=space,
            query_embedding=[float(x) for x in query_embedding],
            top_k=top_k,
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(
                SEARCH_VECTORS_URL,
                json=req.model_dump(mode="json"),
                timeout=300,
            ) as resp:
                payload = await resp.json()
                if resp.status != 200:
                    raise ValueError(f"search_vectors HTTP {resp.status}: {payload}")

        data = SearchVectorsResponse.model_validate(payload)
        if not data.success:
            raise ValueError(f"search_vectors failed: {data.message}")

        yield {
            output_key: data.model_dump(mode="json"),
            output_chunk_ids_key: [str(cid) for cid in data.chunk_ids],
        }

    return node

