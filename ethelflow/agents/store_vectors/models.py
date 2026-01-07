from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional
import uuid


class StoreVectorsRequest(BaseModel):
    chunk_ids: List[uuid.UUID]
    embeddings: List[List[float]]

    # New routing inputs
    tenant: str = Field(..., min_length=1)
    space: Optional[str] = None  # if None, use tenant default from catalog

    # Backward compat (discouraged): if callers still send this, we can map it.
    model_name: Optional[str] = None


class StoreVectorsResponse(BaseModel):
    success: bool
    message: str = ""
    num_vectors_stored: int = 0

    # What was used
    tenant: Optional[str] = None
    space: Optional[str] = None
    store_table: Optional[str] = None

