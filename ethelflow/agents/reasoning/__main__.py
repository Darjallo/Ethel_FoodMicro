import base64
import io
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from openai import AsyncAzureOpenAI

from ethelflow.agents.reasoning.models import ReasoningRequest, ReasoningResponse
from ethelflow.assets.s3 import s3_manager
from ethelflow.settings.reasoning_settings import settings as reasoning_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncAzureOpenAI(
        azure_endpoint=reasoning_settings.azure_endpoint,
        api_version=reasoning_settings.api_version,
        api_key=reasoning_settings.api_key,
    )
    app.state.client = client
    await s3_manager.init()

    yield
    await s3_manager.close()
    await client.close()


app = FastAPI(lifespan=lifespan)


async def get_client(request: Request) -> AsyncAzureOpenAI:
    client: AsyncAzureOpenAI = request.app.state.client
    if not client:
        raise ValueError("Azure OpenAI client is not initialized.")
    return client


async def stream_generator(response_stream):
    async for chunk in response_stream:
        if chunk.choices and chunk.choices[0].delta:
            content = chunk.choices[0].delta.content
            if content:
                yield content


@app.post("/reasoning_with_document")
async def reasoning_with_document(
    req: ReasoningRequest,
    client: AsyncAzureOpenAI = Depends(get_client),
):
    if req.images:
        base64_items = [(img.content_type, img.data_base64) for img in req.images]
    elif req.document_ids:
        document_ids = req.document_ids
        content_types = req.content_types or []
        if len(content_types) != len(document_ids):
            raise HTTPException(
                status_code=400, detail="content_types must match document_ids length"
            )
        base64_items = []
        for document_id, content_type in zip(document_ids, content_types):
            if not content_type.startswith("image/"):
                raise NotImplementedError(f"Unsupported content type: {content_type}")
            file_object = io.BytesIO()
            await s3_manager.download_file(str(document_id), file_object)
            file_object.seek(0)
            base64_items.append(
                (content_type, base64.b64encode(file_object.read()).decode("utf-8"))
            )
    elif req.document_id:
        if req.document_id is None or req.content_type is None:
            raise HTTPException(
                status_code=400, detail="document_id and content_type are required"
            )
        file_object = io.BytesIO()
        await s3_manager.download_file(str(req.document_id), file_object)
        file_object.seek(0)
        file_content = file_object.read()
        base64_items = [
            (req.content_type, base64.b64encode(file_content).decode("utf-8"))
        ]
    else:
        base64_items = []

    messages = list(req.messages or [])
    if req.prompt is not None or not messages:
        base_message = {
            "role": "user",
            "content": [{"type": "text", "text": req.prompt or ""}],
        }
        for content_type, content_b64 in base64_items:
            base_message["content"].append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{content_type};base64,{content_b64}"},
                }
            )
        messages.append(base_message)
    else:
        # attach images to the last message
        last_message = messages[-1]
        last_content = last_message.setdefault("content", [])
        if isinstance(last_content, str):
            last_message["content"] = [{"type": "text", "text": last_content}]
            last_content = last_message["content"]
        for content_type, content_b64 in base64_items:
            last_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{content_type};base64,{content_b64}"},
                }
            )

    # 3. Call Azure OpenAI
    completion_params = {
        "model": req.deployment,
        "messages": messages,
        "max_completion_tokens": 4096,
        "stream": req.stream,
    }
    if req.reasoning_effort is not None:
        completion_params["reasoning_effort"] = req.reasoning_effort

    response = await client.chat.completions.create(**completion_params)

    if req.stream:
        return StreamingResponse(
            stream_generator(response), media_type="text/event-stream"
        )
    else:
        return ReasoningResponse(response=response.choices[0].message.content)


# plain prompt, without document
@app.post("/reasoning")
async def reasoning(
    req: ReasoningRequest,
    client: AsyncAzureOpenAI = Depends(get_client),
):
    # 1. Prepare the payload for Azure OpenAI
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": req.prompt},
            ],
        }
    ]

    # 2. Call Azure OpenAI
    completion_params = {
        "model": req.deployment,
        "messages": messages,
        "max_completion_tokens": 4096,
        "stream": req.stream,
    }
    if req.reasoning_effort is not None:
        completion_params["reasoning_effort"] = req.reasoning_effort

    response = await client.chat.completions.create(**completion_params)

    if req.stream:
        return StreamingResponse(
            stream_generator(response), media_type="text/event-stream"
        )
    else:
        return ReasoningResponse(response=response.choices[0].message.content)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
