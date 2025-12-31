from pydantic import BaseModel
from typing import Literal
import uuid


class InlineImage(BaseModel):
    content_type: str
    data_base64: str


class ReasoningRequest(BaseModel):
    # If a document_id is provided, the etheldocument with the ID is provided to the reasoning context
    document_id: uuid.UUID | None = None
    content_type: str | None = None
    document_ids: list[uuid.UUID] | None = None
    content_types: list[str] | None = None
    images: list[InlineImage] | None = None

    # Prompt will be used as the last user messages in the chat completion
    prompt: str | None = None

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

        if self.prompt is None and (self.messages is None or len(self.messages) == 0):
            raise ValueError("Either prompt or messages must be provided")

        if self.prompt is not None and self.messages is not None:
            raise ValueError("Only one of prompt or messages can be provided")


class ReasoningResponse(BaseModel):
    response: str
