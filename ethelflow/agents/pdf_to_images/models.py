import uuid
from typing import List

from pydantic import BaseModel


class PdfToImagesRequest(BaseModel):
    document_id: uuid.UUID
    dpi: int = 300


class PdfToImagesPage(BaseModel):
    page_number: int
    content_type: str = "image/png"
    data_base64: str


class PdfToImagesResponse(BaseModel):
    pages: List[PdfToImagesPage]
