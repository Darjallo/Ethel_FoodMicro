from __future__ import annotations

import uuid
from typing import List, Optional

from pydantic import BaseModel, Field


class SearchVectorsRequest(BaseModel):
    document_ids: List[uuid.UUID] = Field(..., min_length=1)
    extractor: str = Field(..., min_length=1)
    method: str = Field(..., min_length=1)

    tenant: str = Field(..., min_length=1)
    space: Optional[str] = None  # if None, use tenant default from catalog

    query_embedding: List[float]
    top_k: int = Field(default=10, ge=1, le=200)


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    distance: float


class SearchVectorsResponse(BaseModel):
    success: bool
    message: str = ""

    tenant: Optional[str] = None
    space: Optional[str] = None
    store_table: Optional[str] = None

    hits: List[SearchHit] = Field(default_factory=list)
    chunk_ids: List[uuid.UUID] = Field(default_factory=list)  # convenience mirror

