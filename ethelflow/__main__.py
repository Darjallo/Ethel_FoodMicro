from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from sqlmodel import Session, create_engine
from ethelflow.settings.postgres_settings import postgres_settings
from ethelflow.data.models import EthelDocument
from ethelflow.assets.s3 import s3_manager
import uuid

# from alembic.config import Config
# from alembic import command

from ethelflow.models import FlowRequest
from ethelflow.handler import handler, handler_stream
from ethelflow.flows.flow_resume import runs

import sys
import importlib

from uuid import UUID

app = FastAPI()

engine = create_engine(postgres_settings.url)


def get_session():
    with Session(engine) as session:
        yield session


# an endpoint to get the "run" with a specific id (GET /run/{run_id})
@app.get("/flow/{run_id}")
async def get_run(run_id: UUID):
    doc = runs.find_one({"_id": run_id}, projection={"state": False})
    if not doc:  # return 404 if run not found
        raise HTTPException(status_code=404, detail="Run not found")

    return doc


# add a file to the etheldocuments table (POST /documents)
# example curl command (file name url-encoded):
# curl -X POST "http://localhost:8080/documents?title=Applied%20Security%20Lab%202023" -F "file=@asl-book-as2023.pdf"
@app.post("/documents")
async def create_document(
    title: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    object_name = str(uuid.uuid4())
    try:
        s3_manager.upload_file(file.file, object_name)
        file.content_type
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload asset: {e}")

    try:
        document = EthelDocument(
            id=object_name, title=title, content_type=file.content_type
        )
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


@app.post("/flow")
async def create_flow(flow_request: FlowRequest):
    """
    Endpoint to create a flow execution request.
    """
    if flow_request.flow_reload:
        sys.modules.pop(f"ethelflow.flows.{flow_request.flow}", None)
    mod = importlib.import_module(f"ethelflow.flows.{flow_request.flow}")

    if flow_request.stream:
        return handler_stream(
            mod,
            flow_request.context,
            flow_request.query,
            flow_request.file_id,
            flow_request.flow,
        )
    else:
        return await handler(
            mod,
            flow_request.context,
            flow_request.query,
            flow_request.file_id,
            flow_request.flow,
        )


if __name__ == "__main__":
    import uvicorn

    # TODO: run alembic migrations programmatically on startup
    # alembic_cfg = Config()
    # alembic_cfg.set_main_option("script_location", "alembic")
    # alembic_cfg.set_main_option("sqlalchemy.url", postgres_settings.url)
    # command.upgrade(alembic_cfg, "head")

    uvicorn.run(app, host="0.0.0.0", port=8080)
