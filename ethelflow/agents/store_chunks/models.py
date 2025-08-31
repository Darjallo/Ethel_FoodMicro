from pydantic import BaseModel
from typing import List
import uuid


class StoreChunksRequest(BaseModel):
    document_id: uuid.UUID
    chunks: List[str]
    method: str


class StoreChunksResponse(BaseModel):
    success: bool
    message: str = ""
    chunk_set_id: uuid.UUID | None = None
    chunk_ids: List[uuid.UUID] = []
