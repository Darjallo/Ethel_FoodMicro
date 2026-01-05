from typing import List, Optional
import uuid

from pydantic import BaseModel, Field


class StoreChunksRequest(BaseModel):
    # chunksets hang off document_texts.id
    text_id: uuid.UUID
    chunks: List[str]
    method: str

    # If true, delete any existing chunksets for (text_id, method) first
    replace: bool = True


class StoreChunksResponse(BaseModel):
    success: bool
    message: str = ""
    chunk_set_id: Optional[uuid.UUID] = None
    chunk_ids: List[uuid.UUID] = Field(default_factory=list)

