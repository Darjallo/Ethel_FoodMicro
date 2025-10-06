from collections import defaultdict
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, create_engine
from ethelflow.settings.postgres_settings import postgres_settings
from ethelflow.data.models import EthelDocument
from ethelflow.assets.s3 import s3_manager
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import asyncio
import uuid
import json

# from alembic.config import Config
# from alembic import command

from ethelflow.models import FlowRequest
from ethelflow.handler import handler

import sys
import importlib

from uuid import UUID


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with AsyncPostgresSaver.from_conn_string(
        postgres_settings.db_url
    ) as checkpointer:
        await checkpointer.setup()
        print("Checkpointer setup complete.")

    pool = AsyncConnectionPool(conninfo=postgres_settings.db_url, open=False)
    await pool.open()
    checkpointer = AsyncPostgresSaver(pool)
    app.state.checkpointer = checkpointer
    yield

    await pool.close()


app = FastAPI(lifespan=lifespan)

engine = create_engine(postgres_settings.url)


def get_session():
    with Session(engine) as session:
        yield session


# get all checkpoints for a given thread ID
@app.get("/flow/{run_id}/history")
async def get_run_history(
    run_id: UUID,
    checkpointer: AsyncPostgresSaver = Depends(lambda: app.state.checkpointer),
):
    checkpoints = [
        checkpoint
        async for checkpoint in checkpointer.alist(
            {"configurable": {"thread_id": str(run_id)}}
        )
    ]
    return checkpoints


# get the latest checkpoint for a given thread ID
@app.get("/flow/{run_id}/status")
async def get_run_status(
    run_id: UUID,
    checkpointer: AsyncPostgresSaver = Depends(lambda: app.state.checkpointer),
):
    checkpoint = await checkpointer.aget_tuple(
        {"configurable": {"thread_id": str(run_id)}}
    )
    return checkpoint


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
async def run_flow(flow_request: FlowRequest):
    """
    Endpoint to run a flow and return the results.
    """
    if flow_request.flow_reload:
        sys.modules.pop(f"ethelflow.flows.{flow_request.flow}", None)
    mod = importlib.import_module(f"ethelflow.flows.{flow_request.flow}")

    return await handler(
        mod,
        flow_request.context,
        flow_request.query,
        flow_request.file_id,
        flow_request.stream,
        app.state.checkpointer,
    )


# Very basic in-memory asyncio queue to stream flow events via SSE
# FIXME only works within a single instance, needs a distributed queue like Redis for multiple instances
flow_streams = defaultdict(asyncio.Queue)


@app.post("/flow/start")
async def start_flow(flow_request: FlowRequest):
    """
    Endpoint to start a flow and return its ID.
    The ID can later be used to attach to the flow and get updates.
    """
    if flow_request.flow_reload:
        sys.modules.pop(f"ethelflow.flows.{flow_request.flow}", None)
    mod = importlib.import_module(f"ethelflow.flows.{flow_request.flow}")
    thread_id = uuid.uuid4()

    async def run():
        # emit SSE start event
        flow_streams[thread_id].put("event: start\n data: {}\n\n")
        async for event in mod.run(
            thread_id=thread_id,
            context=flow_request.context,
            query=flow_request.query,
            file_id=flow_request.file_id,
            stream=True,
            checkpointer=app.state.checkpointer,
        ):
            await flow_streams[thread_id].put(event)
        await flow_streams[thread_id].put(None)  # Signal completion

    asyncio.create_task(run())

    return {"run_id": thread_id}


@app.get("/flow/{run_id}/attach")
async def attach(run_id: UUID):
    """
    Endpoint to attach to a running flow and get its updates (SSE).
    # FIXME This will only work for flows with streaming enabled. needs a check for that
    # FIXME Currently, if the flow has already completed, this will hang forever. needs a timeout or a check for completion
    """

    queue = flow_streams.get(run_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Run ID not found")

    async def event_stream():
        while True:
            event = await queue.get()
            if event is None:
                yield "event: complete\n data: {}\n\n"
                break
            yield f"event: stream\n data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    # TODO: run alembic migrations programmatically on startup
    # alembic_cfg = Config()
    # alembic_cfg.set_main_option("script_location", "alembic")
    # alembic_cfg.set_main_option("sqlalchemy.url", postgres_settings.url)
    # command.upgrade(alembic_cfg, "head")

    uvicorn.run(app, host="0.0.0.0", port=8080)
