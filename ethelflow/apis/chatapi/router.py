from __future__ import annotations

import importlib
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from ethelflow.handler import handler
from ethelflow.apis.common.deps import get_checkpointer, get_pod_store
from ethelflow.data.pods import PodConflict, PodNotFound, PodStore

from .schemas import ChatCompletionsRequest, ResponsesRequest

router = APIRouter(prefix="/v1", tags=["ChatAPI"])

OWNER_API = "chatapi"
POD_TYPE = "conversation_context"
DEFAULT_TENANT = "ethz"
DEFAULT_FLOW = "rag_intent_chat"


def _strip_debug(ctx: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(ctx or {})
    out.pop("debug", None)
    return out


def _ensure_thread_id(ctx: Dict[str, Any]) -> uuid.UUID:
    raw = ctx.get("_thread_id")
    if isinstance(raw, str):
        try:
            return uuid.UUID(raw)
        except Exception:
            pass
    tid = uuid.uuid4()
    ctx["_thread_id"] = str(tid)
    return tid


async def _run_flow_once(
    *,
    flow_name: str,
    tenant: str,
    ctx: Dict[str, Any],
    checkpointer: AsyncPostgresSaver,
) -> Dict[str, Any]:
    mod = importlib.import_module(f"ethelflow.flows.{flow_name}")

    # mirror /flow behavior: tenant must be in context
    ctx = dict(ctx or {})
    ctx["tenant"] = tenant

    thread_id = _ensure_thread_id(ctx)

    result = await handler(
        mod=mod,
        context=ctx,
        stream=False,              # start non-streaming; add streaming later
        checkpointer=checkpointer,
        thread_id=thread_id,
        command=None,
    )
    if not isinstance(result, dict):
        raise RuntimeError(f"Unexpected flow result type: {type(result)}")
    return result


@router.post("/chat/completions")
async def chat_completions(
    req: ChatCompletionsRequest,
    resp: Response,
    x_pod_id: Optional[str] = Header(default=None, alias="X-Pod-Id"),
    x_tenant: Optional[str] = Header(default=None, alias="X-Tenant"),
    pod_store: PodStore = Depends(get_pod_store),
    checkpointer: AsyncPostgresSaver = Depends(get_checkpointer),
):
    tenant = (x_tenant or req.metadata.get("tenant") or DEFAULT_TENANT).strip()
    end_user_id = req.user or req.metadata.get("end_user_id") or None

    # Determine pod_id (capability handle)
    pod_id_raw = req.metadata.get("pod_id") or x_pod_id
    pod = None

    if pod_id_raw:
        try:
            pod_uuid = uuid.UUID(str(pod_id_raw))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid pod_id")
        try:
            pod = await pod_store.get_pod(pod_id=pod_uuid, tenant=tenant, owner_api=OWNER_API)
        except PodNotFound:
            raise HTTPException(status_code=404, detail="Pod not found")
        ctx = dict(pod.data or {})
    else:
        # Create a new pod with a minimal canonical context
        initial_ctx = req.metadata.get("initial_context")
        if isinstance(initial_ctx, dict):
            ctx = dict(initial_ctx)
        else:
            ctx = {"messages": [], "routing_state": {}, "intent_options": {}, "rag": {}, "debug": {}}

        pod = await pod_store.create_pod(
            tenant=tenant,
            owner_api=OWNER_API,
            pod_type=POD_TYPE,
            end_user_id=end_user_id,
            data=_strip_debug(ctx),
        )

    # Append incoming messages as delta (client can be memoryless)
    msgs = ctx.get("messages")
    if not isinstance(msgs, list):
        msgs = []
        ctx["messages"] = msgs

    for m in req.messages:
        # keep permissive; flow expects {"role","content"}-like
        msgs.append({"role": m.role, "content": m.content})

    flow_name = str(req.metadata.get("flow") or DEFAULT_FLOW)

    try:
        result = await _run_flow_once(flow_name=flow_name, tenant=tenant, ctx=ctx, checkpointer=checkpointer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Flow error: {e}")

    ctx_out = result.get("context") if isinstance(result.get("context"), dict) else ctx
    ctx_store = _strip_debug(ctx_out)

    try:
        pod = await pod_store.update_pod(
            pod_id=pod.id,
            tenant=tenant,
            owner_api=OWNER_API,
            data=ctx_store,
            expected_rev=None,
        )
    except PodConflict:
        raise HTTPException(status_code=409, detail="Pod update conflict")

    # Return pod id so a memoryless client can just replay it
    resp.headers["X-Pod-Id"] = str(pod.id)

    answer = result.get("answer")
    if answer is None:
        answer = result.get("output")  # fallback
    if answer is None:
        answer = ""

    # Minimal OpenAI-like shape (+ one extra pod_id field that clients can ignore)
    return {
        "id": f"chatcmpl_{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "pod_id": str(pod.id),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": str(answer)},
                "finish_reason": "stop",
            }
        ],
        # optionally expose debug to test clients without persisting it
        "debug": (ctx_out.get("debug") if isinstance(ctx_out, dict) else None),
    }


@router.post("/responses")
async def responses(
    req: ResponsesRequest,
    resp: Response,
    x_pod_id: Optional[str] = Header(default=None, alias="X-Pod-Id"),
    x_tenant: Optional[str] = Header(default=None, alias="X-Tenant"),
    pod_store: PodStore = Depends(get_pod_store),
    checkpointer: AsyncPostgresSaver = Depends(get_checkpointer),
):
    tenant = (x_tenant or req.metadata.get("tenant") or DEFAULT_TENANT).strip()
    end_user_id = req.user or req.metadata.get("end_user_id") or None

    # In Responses, let "conversation" be our pod_id (opaque handle)
    pod_id_raw = req.conversation or req.metadata.get("pod_id") or x_pod_id
    pod = None

    if pod_id_raw:
        try:
            pod_uuid = uuid.UUID(str(pod_id_raw))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid conversation/pod id")
        try:
            pod = await pod_store.get_pod(pod_id=pod_uuid, tenant=tenant, owner_api=OWNER_API)
        except PodNotFound:
            raise HTTPException(status_code=404, detail="Conversation not found")
        ctx = dict(pod.data or {})
    else:
        initial_ctx = req.metadata.get("initial_context")
        if isinstance(initial_ctx, dict):
            ctx = dict(initial_ctx)
        else:
            ctx = {"messages": [], "routing_state": {}, "intent_options": {}, "rag": {}, "debug": {}}

        pod = await pod_store.create_pod(
            tenant=tenant,
            owner_api=OWNER_API,
            pod_type=POD_TYPE,
            end_user_id=end_user_id,
            data=_strip_debug(ctx),
        )

    # Normalize input into a "user" message turn
    msgs = ctx.get("messages")
    if not isinstance(msgs, list):
        msgs = []
        ctx["messages"] = msgs

    msgs.append({"role": "user", "content": req.input})

    flow_name = str(req.metadata.get("flow") or DEFAULT_FLOW)

    try:
        result = await _run_flow_once(flow_name=flow_name, tenant=tenant, ctx=ctx, checkpointer=checkpointer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Flow error: {e}")

    ctx_out = result.get("context") if isinstance(result.get("context"), dict) else ctx
    ctx_store = _strip_debug(ctx_out)

    try:
        pod = await pod_store.update_pod(
            pod_id=pod.id,
            tenant=tenant,
            owner_api=OWNER_API,
            data=ctx_store,
            expected_rev=None,
        )
    except PodConflict:
        raise HTTPException(status_code=409, detail="Pod update conflict")

    resp.headers["X-Pod-Id"] = str(pod.id)

    answer = result.get("answer")
    if answer is None:
        answer = result.get("output")
    if answer is None:
        answer = ""

    # Minimal Responses-like shape (+ debug visible but not persisted)
    return {
        "id": f"resp_{uuid.uuid4().hex}",
        "object": "response",
        "created_at": int(time.time()),
        "model": req.model,
        "conversation": str(pod.id),
        "output": [
            {
                "id": f"msg_{uuid.uuid4().hex}",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": str(answer)}],
            }
        ],
        "debug": (ctx_out.get("debug") if isinstance(ctx_out, dict) else None),
    }

