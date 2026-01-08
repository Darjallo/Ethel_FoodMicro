from __future__ import annotations

import logging
from typing import Dict, List, Set, Tuple

import sqlalchemy as sa
from fastapi import Depends, FastAPI
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from ethelflow.agents.retrieve_chunks.models import (
    RetrieveChunksRequest,
    RetrieveChunksResponse,
    RetrievedChunk,
)
from ethelflow.data.db_utils import get_session
from ethelflow.data.models import Asset, Chunk, ChunkSet, DocumentText, EthelDocument

logger = logging.getLogger("uvicorn.error")
app = FastAPI()


def _dedupe_preserve_order(ids: List) -> List:
    seen: Set = set()
    out: List = []
    for x in ids:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


@app.post("/retrieve_chunks", response_model=RetrieveChunksResponse)
async def retrieve_chunks(req: RetrieveChunksRequest, session: AsyncSession = Depends(get_session)):
    """
    Given tenant + chunk_ids (possibly with duplicates), return each chunk once,
    filtered to the tenant boundary.

    Tenant boundary is enforced by joining:
      chunks -> chunksets -> document_texts -> etheldocuments -> assets (tenant)
    """
    try:
        if not req.chunk_ids:
            return RetrieveChunksResponse(success=True, tenant=req.tenant, chunks=[], chunk_ids=[])

        # Deduplicate (keep first occurrence order)
        uniq_ids = _dedupe_preserve_order(req.chunk_ids)

        # Guardrail (optional): prevent pathological requests
        if len(uniq_ids) > 2000:
            return RetrieveChunksResponse(
                success=False,
                message=f"Too many chunk_ids ({len(uniq_ids)}). Limit is 2000 per request.",
                tenant=req.tenant,
            )

        stmt = (
            sa.select(
                Chunk.id.label("chunk_id"),
                Chunk.text.label("text"),
                Chunk.position.label("position"),
                DocumentText.document_id.label("document_id"),
            )
            .select_from(Chunk)
            .join(ChunkSet, Chunk.chunk_set_id == ChunkSet.id)
            .join(DocumentText, ChunkSet.text_id == DocumentText.id)
            .join(EthelDocument, DocumentText.document_id == EthelDocument.id)
            .join(Asset, EthelDocument.asset_id == Asset.id)
            .where(Asset.tenant == req.tenant)
            .where(Chunk.id.in_(sa.bindparam("chunk_ids")))
        )

        # Bind types explicitly for asyncpg happiness
        stmt = stmt.params(chunk_ids=uniq_ids).bindparams(
            sa.bindparam(
                "chunk_ids",
                value=uniq_ids,
                type_=postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            )
        )

        res = await session.execute(stmt)
        rows = res.fetchall()

        by_id: Dict = {r.chunk_id: r for r in rows}

        out_chunks: List[RetrievedChunk] = []
        missing: List[str] = []

        for cid in uniq_ids:
            r = by_id.get(cid)
            if r is None:
                missing.append(str(cid))
                continue
            out_chunks.append(
                RetrievedChunk(
                    chunk_id=r.chunk_id,
                    text=r.text,
                    position=int(r.position),
                    document_id=r.document_id,
                )
            )

        msg = ""
        if missing:
            msg = f"{len(missing)} chunk_id(s) not found (or not in tenant scope)."

        return RetrieveChunksResponse(
            success=True,
            message=msg,
            tenant=req.tenant,
            chunks=out_chunks,
            chunk_ids=[c.chunk_id for c in out_chunks],
        )

    except Exception as e:
        logger.exception("retrieve_chunks failed")
        return RetrieveChunksResponse(success=False, message=str(e), tenant=req.tenant)
    

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

