from __future__ import annotations

import uuid
from typing import List, Optional

from pydantic import BaseModel, Field


class RetrieveChunksRequest(BaseModel):
    tenant: str = Field(..., min_length=1)
    chunk_ids: List[uuid.UUID] = Field(..., min_length=1)


class RetrievedChunk(BaseModel):
    chunk_id: uuid.UUID
    text: str
    position: int
    document_id: uuid.UUID


class RetrieveChunksResponse(BaseModel):
    success: bool
    message: str = ""
    tenant: Optional[str] = None

    chunks: List[RetrievedChunk] = Field(default_factory=list)
    chunk_ids: List[uuid.UUID] = Field(default_factory=list)  # convenience mirror

