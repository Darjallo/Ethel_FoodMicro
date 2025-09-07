from pydantic import BaseModel
from typing import Optional, Literal
import uuid


class ReasoningRequest(BaseModel):
    document_id: uuid.UUID
    content_type: str
    prompt: str
    deployment: Optional[str] = "gpt-4o"
    reasoning_effort: Optional[Literal["low", "medium", "high"]] = None


class ReasoningResponse(BaseModel):
    response: str
