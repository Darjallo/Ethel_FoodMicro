from typing import List
from pydantic import BaseModel


class EmbeddingRequest(BaseModel):
    texts: List[str]
    deployment: str
