from pydantic import BaseModel
from typing import List
import uuid


class StoreVectorsRequest(BaseModel):
    chunk_ids: List[uuid.UUID]
    embeddings: List[List[float]]
    model_name: str = "text-embedding-3-large"


class StoreVectorsResponse(BaseModel):
    success: bool
    message: str = ""
    num_vectors_stored: int
