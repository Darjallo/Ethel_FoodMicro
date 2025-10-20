import asyncio
import importlib
import json
import logging
import uuid
from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.base import CheckpointTuple
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Checkpointer, Command

from ethelflow.handler import handler
from ethelflow.models import FlowContinueRequest, FlowRequest

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/flow", tags=["flows"])


async def get_checkpointer(request: Request) -> AsyncPostgresSaver:
    checkpointer: AsyncPostgresSaver = request.app.state.checkpointer
    if not checkpointer:
        raise ValueError("Checkpointer is not initialized")
    return checkpointer


# Continue a flow that has been interrupted and waiting for user input
@router.post("/{run_id}/continue")
async def continue_flow(
    run_id: UUID,
    continue_request: FlowContinueRequest,
    checkpointer: AsyncPostgresSaver = Depends(get_checkpointer),
):
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


@router.post("")
async def run_flow(flow_request: FlowRequest, checkpointer=Depends(get_checkpointer)):
    """
    Endpoint to run a flow and return the results.
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


@router.post("/start")
async def start_flow(
    flow_request: FlowRequest,
    checkpointer: Checkpointer = Depends(get_checkpointer),
):
    """
    Endpoint to start a flow and return its ID.
    The ID can later be used to attach to the flow and get updates.
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


@router.get("/{run_id}/attach")
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
            # XXX: the streaming event name can also be read from event directly, to support different event types
            # a flow could then emit multiple streams that a client distinguishes by event name
            yield f"event: stream\n data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# get all checkpoints for a given thread ID
@router.get("/{run_id}/history")
async def get_run_history(
    run_id: UUID,
    checkpointer: AsyncPostgresSaver = Depends(get_checkpointer),
):
    logger.info(f"Fetching history for run_id: {run_id}")
    checkpoints = [
        checkpoint._asdict()
        async for checkpoint in checkpointer.alist(
            {"configurable": {"thread_id": str(run_id)}}
        )
    ]
    return checkpoints


# get the latest checkpoint for a given thread ID
@router.get("/{run_id}/status")
async def get_run_status(
    run_id: UUID,
    checkpointer: AsyncPostgresSaver = Depends(get_checkpointer),
):
    logger.info(f"Fetching status for run_id: {run_id}")
    checkpoint = await checkpointer.aget_tuple(
        {"configurable": {"thread_id": str(run_id)}}
    )
    return checkpoint._asdict()
