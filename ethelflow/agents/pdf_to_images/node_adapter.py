from typing import Any, AsyncGenerator, Callable, Dict
import aiohttp
import uuid

from ethelflow.agents.pdf_to_images.models import (
    PdfToImagesRequest,
    PdfToImagesResponse,
)

PDF_TO_IMAGES_URL = "http://pdf-to-images.default.svc:8000/pdf_to_images"


def pdf_to_images_node(
    document_id_key: str = "document_id",
    dpi_key: str = "dpi",
    output_key: str = "pages",
) -> Callable[[Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
    async def node(state: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        raw_document_id = state.get(document_id_key)
        if isinstance(raw_document_id, uuid.UUID):
            document_id = raw_document_id
        else:
            try:
                document_id = uuid.UUID(raw_document_id)
            except ValueError as e:
                raise ValueError(
                    f"Invalid UUID format for {document_id_key}: {raw_document_id}"
                ) from e

        dpi = state.get(dpi_key, 300)

        request = PdfToImagesRequest(document_id=document_id, dpi=dpi)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                PDF_TO_IMAGES_URL, json=request.model_dump(mode="json")
            ) as response:
                if response.status != 200:
                    error_detail = await response.text()
                    raise ValueError(
                        f"PDF-to-images service returned status {response.status}: {error_detail}"
                    )
                response_data = await response.json()
                data = PdfToImagesResponse.model_validate(response_data)

        yield {output_key: [page.model_dump(mode="json") for page in data.pages]}

    return node
