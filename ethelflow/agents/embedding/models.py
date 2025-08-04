from typing import List
from pydantic import BaseModel
from openai.types.create_embedding_response import Usage


class EmbeddingRequest(BaseModel):
    texts: List[str]
    deployment: str


class EmbeddingResponse(BaseModel):
    embeddings: List[List[float]]
    model: str
    usage: Usage
