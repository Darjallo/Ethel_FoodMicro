from pydantic import BaseModel
from typing import Literal
import uuid


class ReasoningRequest(BaseModel):
    # If a document_id is provided, the etheldocument with the ID is provided to the reasoning context
    document_id: uuid.UUID | None = None
    content_type: str | None = None

    # Prompt will be used as the last user messages in the chat completion
    prompt: str

    # Additional messages to include in the chat completion
    # Should be a list of dicts with "role" and "content" keys
    messages: list[dict] | None = None
    deployment: str | None = "gpt-4o"
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    stream: bool = False

    # if document_id is provided, content_type must also be provided
    def validate(self):
        if self.document_id and not self.content_type:
            raise ValueError("content_type must be provided if document_id is provided")


class ReasoningResponse(BaseModel):
    response: str
