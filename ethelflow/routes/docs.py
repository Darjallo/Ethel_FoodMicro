import logging
import uuid
from io import BytesIO
from typing import AsyncGenerator

import magic
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ethelflow.assets.s3 import s3_manager
from ethelflow.data.models import EthelDocument
from ethelflow.settings.postgres_settings import postgres_settings

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/docs", tags=["docs"])

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


# add a file to the etheldocuments table (POST /docs)
# example curl command (file name url-encoded):
# curl -X POST "http://localhost:8080/docs?title=Applied%20Security%20Lab%202023" -F "file=@asl-book-as2023.pdf"
@router.post("")
async def create_document(
    title: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    data = BytesIO(await file.read())
    object_name = str(uuid.uuid4())

    mime = magic.Magic(mime=True)
    content_type = mime.from_buffer(data.getvalue())
    try:
        s3_manager.upload_file(data, object_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload asset: {e}")

    # save the document to DB
    try:
        document = EthelDocument(id=object_name, title=title, content_type=content_type)
        session.add(document)
        await session.commit()
        await session.refresh(document)
        return document
    except Exception as e:
        # If DB operation fails, try to clean up the orphaned S3 object.
        try:
            s3_manager.delete_file(object_name)
        except Exception as asset_delete_error:
            # Log that cleanup failed, manual intervention might be needed.
            logger.error(
                f"CRITICAL: Failed to delete orphaned S3 object {object_name} after DB error. Error: {asset_delete_error}"
            )

        await session.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to create database record: {e}"
        )
