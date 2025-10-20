import io
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from ethelflow.agents.file_to_text.models import FileToTextRequest, FileToTextResponse
from ethelflow.assets.s3 import s3_manager
from ethelflow.data.models import EthelDocument
from ethelflow.settings.postgres_settings import postgres_settings

AsyncSessionLocal: sessionmaker[AsyncSession] = sessionmaker(
    create_async_engine(
        postgres_settings.async_url,
        pool_size=20,
        max_overflow=20,
    ),
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


app = FastAPI()


@app.post("/file_to_text", response_model=FileToTextResponse)
async def file_to_text(
    req: FileToTextRequest, session: AsyncSession = Depends(get_session)
):
    statement = select(EthelDocument).where(EthelDocument.id == req.document_id)
    document = (await session.execute(statement)).scalars().one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.content_type not in ["application/pdf", "text/plain", "text/html"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content type: {document.content_type}",
        )

    try:
        file_object = io.BytesIO()
        s3_manager.download_file(str(document.id), file_object)
        file_object.seek(0)

        text = ""
        if document.content_type == "application/pdf":
            reader = PdfReader(file_object)
            for page in reader.pages:
                text += page.extract_text() or ""
        elif document.content_type in ["text/plain", "text/html"]:
            text = file_object.read().decode("utf-8")

        return FileToTextResponse(text=text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
