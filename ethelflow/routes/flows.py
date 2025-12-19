import asyncio
import importlib
import json
import logging
import uuid
from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.base import CheckpointTuple
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Checkpointer, Command

from ethelflow.handler import handler
from ethelflow.models import FlowContinueRequest, FlowRequest

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/flow", tags=["Flows"])



async def get_checkpointer(request: Request) -> AsyncPostgresSaver:
    checkpointer: AsyncPostgresSaver = request.app.state.checkpointer
    if not checkpointer:
        raise ValueError("Checkpointer is not initialized")
    return checkpointer


# Continue a flow that has been interrupted and waiting for user input
@router.post(
    "/{run_id}/continue",
    summary="Continue Flow",
)
async def continue_flow(
    run_id: UUID = Path(
            ...,
            description="Identifier of the flow run returned by `/flow/start`.",
            example="b7e7a6b0-2d73-4f4c-a8f2-8baf9a6a5c2e",
        ),
    continue_request: FlowContinueRequest = Body(
        ...,
        description="Continuation data used to resume an interrupted flow.",
        example={
            "data": {"interrupt_id": {"key": "value"}},
            "stream": False,
        },
    ),
    checkpointer=Depends(get_checkpointer),
):
    """
    Resume a paused or interrupted flow run.

    This endpoint is used when a flow requires additional input before it can continue.

    ### Behavior
    - If `stream=false`, the request returns the next output produced by the flow.
    - If `stream=true`, the response is streamed as JSON update events.
    """
    checkpoint: CheckpointTuple = await checkpointer.aget_tuple(
        {"configurable": {"thread_id": str(run_id)}}
    )
    if checkpoint is None:
        raise HTTPException(status_code=404, detail="Run ID not found")

    # Restore state from the checkpoint
    context = checkpoint.checkpoint.get("channel_values")

    # Retrieve the compiled graph with the flow name from the metadata
    mod = importlib.import_module(f"ethelflow.flows.{checkpoint.metadata.get('flow')}")
    logger.info(
        f"Continuing flow {checkpoint.metadata.get('flow')} for run_id: {run_id}"
    )

    command = Command(resume=continue_request.data)
    return await handler(
        mod=mod,
        context=context,
        stream=continue_request.stream,
        checkpointer=checkpointer,
        thread_id=run_id,
        command=command,
    )


@router.post(
    "",
    summary="Run Flow",
)
async def run_flow(
    flow_request: FlowRequest = Body(
        ...,
        description="Flow execution request defining which flow to run and its initial context.",
        example={
            "flow": "example_flow",
            "tenant": "tenant_id",
            "context": {"user_message": "Hello"},
            "stream": False,
        },
    ),
    checkpointer=Depends(get_checkpointer),
):
    """
    Execute a flow to completion in a single request.

    Use this endpoint when you want to run a flow immediately without explicitly managing a run lifecycle.

    ### Behavior
    - If `stream=false`, the request returns the first output produced by the flow.
    - If `stream=true`, the response is streamed as JSON update events.

    The flow state is persisted using the configured checkpointer.
    """
    mod = importlib.import_module(f"ethelflow.flows.{flow_request.flow}")

    thread_id = uuid.uuid4()
    logger.info(f"Starting flow {flow_request.flow} with run_id: {thread_id}")

    return await handler(
        mod=mod,
        context=flow_request.context,
        stream=flow_request.stream,
        checkpointer=checkpointer,
        thread_id=thread_id,
        command=None,
    )


# Very basic in-memory asyncio queue to stream flow events via SSE
# FIXME only works within a single instance, needs a distributed queue like Redis for multiple instances
flow_streams = defaultdict(asyncio.Queue)


@router.post(
    "/start",
    summary="Start Flow",
)
async def start_flow(
    flow_request: FlowRequest = Body(
        ...,
        description="Configuration and initial context used to start a new flow run.",
        example={
            "flow": "example_flow",
            "tenant": "tenant_id",
            "context": {"user_message": "Hello"},
            "stream": False,
        },
    ),
    checkpointer=Depends(get_checkpointer),
):
    """
    Start a new flow run and return a `run_id`.

    Use this endpoint when you want to:
    - create a flow run first
    - then continue it later using `/flow/{run_id}/continue`

    The returned `run_id` uniquely identifies the flow execution.
    """
    mod = importlib.import_module(f"ethelflow.flows.{flow_request.flow}")
    thread_id = uuid.uuid4()

    async def run():
        # emit SSE start event
        await flow_streams[thread_id].put("event: start\n data: {}\n\n")
        async for event in mod.run(
            thread_id=thread_id,
            context=flow_request.context,
            stream=True,
            checkpointer=checkpointer,
        ):
            await flow_streams[thread_id].put(event)
        await flow_streams[thread_id].put(None)  # Signal completion

    asyncio.create_task(run())

    return {"run_id": thread_id}


@router.get(
    "/{run_id}/attach",
    summary="Attach to Flow (SSE)",
)
async def attach(
    run_id: UUID = Path(
        ...,
        description="Identifier of the flow run to attach to.",
        example="b7e7a6b0-2d73-4f4c-a8f2-8baf9a6a5c2e",
    ),
):
    """
    Attach to a running flow and receive live updates via Server-Sent Events (SSE).

    This endpoint emits `text/event-stream` data and is intended for browser or UI clients.
    In contrast, streaming responses from `/flow` and `/flow/{run_id}/continue` return
    JSON update chunks over an HTTP response.

    Notes:
    - Works only for flows started with streaming enabled.
    - If the flow has already completed, the stream may remain idle.

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
            # XXX: the streaming event name can also be read from event directly, to support different event types
            # a flow could then emit multiple streams that a client distinguishes by event name
            yield f"event: stream\n data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# get all checkpoints for a given thread ID
@router.get(
    "/{run_id}/history",
    summary="Get Flow History",
)
async def get_run_history(
    run_id: UUID = Path(
        ...,
        description="Identifier of the flow run.",
        example="b7e7a6b0-2d73-4f4c-a8f2-8baf9a6a5c2e",
    ),
    checkpointer=Depends(get_checkpointer),
):
    """
    Retrieve the full execution history for a flow run.

    This includes all persisted checkpoints produced during the flow execution,
    as stored by the configured Postgres-backed checkpointer.
    """
    logger.info(f"Fetching history for run_id: {run_id}")
    checkpoints = [
        checkpoint._asdict()
        async for checkpoint in checkpointer.alist(
            {"configurable": {"thread_id": str(run_id)}}
        )
    ]
    return checkpoints


# get the latest checkpoint for a given thread ID
@router.get(
    "/{run_id}/status",
    summary="Get Flow Status",
)
async def get_run_status(
    run_id: UUID = Path(
        ...,
        description="Identifier of the flow run.",
        example="b7e7a6b0-2d73-4f4c-a8f2-8baf9a6a5c2e",
    ),
    checkpointer=Depends(get_checkpointer),
):
    """
    Retrieve the latest checkpoint for a flow run.

    This endpoint returns the most recent persisted state of the flow,
    which can be used to determine its current execution status.
    """
    logger.info(f"Fetching status for run_id: {run_id}")
    checkpoint = await checkpointer.aget_tuple(
        {"configurable": {"thread_id": str(run_id)}}
    )
    return checkpoint._asdict()
