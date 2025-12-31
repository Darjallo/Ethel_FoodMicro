import base64
import io
from contextlib import asynccontextmanager

import fitz
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ethelflow.agents.pdf_to_images.models import (
    PdfToImagesRequest,
    PdfToImagesResponse,
    PdfToImagesPage,
)
from ethelflow.assets.s3 import s3_manager
from ethelflow.data.db_utils import get_session
from ethelflow.data.models import EthelDocument


@asynccontextmanager
async def lifespan(app: FastAPI):
    await s3_manager.init()
    yield
    await s3_manager.close()


app = FastAPI(lifespan=lifespan)


@app.post("/pdf_to_images", response_model=PdfToImagesResponse)
async def pdf_to_images(
    req: PdfToImagesRequest,
    session: AsyncSession = Depends(get_session),
):
    statement = select(EthelDocument).where(EthelDocument.id == req.document_id)
    document = (await session.execute(statement)).scalars().one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content type: {document.content_type}",
        )

    try:
        file_object = io.BytesIO()
        await s3_manager.download_file(str(document.id), file_object)
        file_object.seek(0)
        file_content = file_object.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download PDF: {e}")

    try:
        pdf = fitz.open(stream=file_content, filetype="pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open PDF: {e}")

    created_pages: list[PdfToImagesPage] = []
    zoom = req.dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    try:
        for index in range(pdf.page_count):
            page = pdf.load_page(index)
            pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
            png_bytes = pix.tobytes("png")

            data_base64 = base64.b64encode(png_bytes).decode("utf-8")
            created_pages.append(
                PdfToImagesPage(
                    page_number=index + 1,
                    content_type="image/png",
                    data_base64=data_base64,
                )
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create images: {e}")
    finally:
        pdf.close()

    return PdfToImagesResponse(pages=created_pages)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
