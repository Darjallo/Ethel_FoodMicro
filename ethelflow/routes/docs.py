import logging
import uuid
from io import BytesIO

import magic
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, create_engine

from ethelflow.assets.s3 import s3_manager
from ethelflow.data.models import EthelDocument
from ethelflow.settings.postgres_settings import postgres_settings

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/docs", tags=["docs"])

engine = create_engine(postgres_settings.url)


def get_session():
    with Session(engine) as session:
        yield session


# add a file to the etheldocuments table (POST /docs)
# example curl command (file name url-encoded):
# curl -X POST "http://localhost:8080/docs?title=Applied%20Security%20Lab%202023" -F "file=@asl-book-as2023.pdf"
@router.post("")
async def create_document(
    title: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
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
        session.commit()
        session.refresh(document)
        return document
    except Exception as e:
        # If DB operation fails, try to clean up the orphaned S3 object.
        try:
            s3_manager.delete_file(object_name)
        except Exception as asset_delete_error:
            # Log that cleanup failed, manual intervention might be needed.
            print(
                f"CRITICAL: Failed to delete orphaned S3 object {object_name} after DB error. Error: {asset_delete_error}"
            )

        session.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to create database record: {e}"
        )
