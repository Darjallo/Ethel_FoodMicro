import logging
import uuid
from io import BytesIO

import magic
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ethelflow.assets.s3 import s3_manager
from ethelflow.data.db_utils import get_session
from ethelflow.data.models import EthelDocument

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/assets", tags=["Assets"])


# add a file to the etheldocuments table (POST /assets)
# example curl command (file name url-encoded):
# curl -X POST "http://localhost:8080/assets?title=Applied%20Security%20Lab%202023" -F "file=@asl-book-as2023.pdf"
@router.post(
    "",
    summary="Create Document",
)
async def create_document(
    title: str = Query(
        ...,
        description="Human-readable title for the document.",
        example="Applied Security Lab 2023",
    ),
    file: UploadFile = File(
        ...,
        description="The file to upload (PDF, image, etc.). Sent as multipart/form-data.",
    ),
    session: AsyncSession = Depends(get_session),
):
    """
    This module provides API endpoints for document upload and metadata persistence.

    Uploaded files are validated, their MIME type is detected from raw bytes, and the file is stored in an S3-compatible backend. Associated metadata is then persisted to PostgreSQL using the `EthelDocument` ORM model.

    ### Processing Flow
    1. **Read file bytes**
    2. **Generate object ID**
    3. **Detect MIME type**
    4. **Upload to S3**
    5. **Persist metadata**
    6. **Error handling and cleanup**
    """

    data = BytesIO(await file.read())
    object_name = str(uuid.uuid4())

    mime = magic.Magic(mime=True)
    content_type = mime.from_buffer(data.getvalue())
    try:
        await s3_manager.upload_file(data, object_name)
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
            await s3_manager.delete_file(object_name)
        except Exception as asset_delete_error:
            # Log that cleanup failed, manual intervention might be needed.
            logger.error(
                f"CRITICAL: Failed to delete orphaned S3 object {object_name} after DB error. Error: {asset_delete_error}"
            )

        await session.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to create database record: {e}"
        )
