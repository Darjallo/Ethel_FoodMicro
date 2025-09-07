from fastapi import FastAPI, Depends, Request
from ethelflow.agents.reasoning.models import ReasoningRequest, ReasoningResponse
from ethelflow.settings.reasoning_settings import settings as reasoning_settings
from ethelflow.assets.s3 import s3_manager
from openai import AsyncAzureOpenAI
from contextlib import asynccontextmanager
import io
import base64


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncAzureOpenAI(
        azure_endpoint=reasoning_settings.azure_endpoint,
        api_version=reasoning_settings.api_version,
        api_key=reasoning_settings.api_key,
    )
    app.state.client = client
    yield
    await client.close()


app = FastAPI(lifespan=lifespan)


async def get_client(request: Request) -> AsyncAzureOpenAI:
    client: AsyncAzureOpenAI = request.app.state.client
    if not client:
        raise ValueError("Azure OpenAI client is not initialized.")
    return client


@app.post("/reasoning")
async def reason(
    req: ReasoningRequest,
    client: AsyncAzureOpenAI = Depends(get_client),
) -> ReasoningResponse:
    # 1. Download the file from S3
    file_object = io.BytesIO()
    s3_manager.download_file(str(req.document_id), file_object)
    file_object.seek(0)
    file_content = file_object.read()

    # 2. Prepare the payload for Azure OpenAI
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": req.prompt},
            ],
        }
    ]

    if req.content_type.startswith("image/"):
        base64_image = base64.b64encode(file_content).decode("utf-8")
        messages[0]["content"].append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{req.content_type};base64,{base64_image}"},
            }
        )
    elif req.content_type == "application/pdf":
        raise NotImplementedError("PDF processing is not yet implemented")
    else:
        raise NotImplementedError(f"Unsupported content type: {req.content_type}")

    completion_params = {
        "model": req.deployment,
        "messages": messages,
        "max_completion_tokens": 4096,
    }
    if req.reasoning_effort is not None:
        completion_params["reasoning_effort"] = req.reasoning_effort

    response = await client.chat.completions.create(**completion_params)

    return ReasoningResponse(response=response.choices[0].message.content)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
