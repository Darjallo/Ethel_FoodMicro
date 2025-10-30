import asyncio
import random
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from openai import (
    AsyncAzureOpenAI,
    RateLimitError,
    APITimeoutError,
    APIError,
)

from ethelflow.agents.embedding.models import EmbeddingRequest, EmbeddingResponse
from ethelflow.settings.embedding_settings import settings as embedding_settings

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncAzureOpenAI(
        azure_endpoint=embedding_settings.azure_endpoint,
        api_version=embedding_settings.api_version,
        api_key=embedding_settings.api_key,
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


MAX_RETRY_TIME = 30.0
MAX_RETRIES = 11
BASE_DELAY = 2.0


async def with_backoff(fn, *args, **kwargs):
    """Retry wrapper that uses the max of Retry-After and exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            return await fn(*args, **kwargs)
        except (
            RateLimitError,
            APITimeoutError,
            APIError,
        ) as e:
            status_code = getattr(e, "status_code", None)
            if status_code not in (429, 500, 503):
                raise

            # Get Retry-After from headers if available
            retry_after_header = None
            if hasattr(e, "response") and e.response is not None:
                headers = getattr(e.response, "headers", {}) or {}
                retry_after_header = headers.get("Retry-After")

            retry_after = None
            if retry_after_header:
                try:
                    retry_after = float(retry_after_header)
                except ValueError:
                    retry_after = None

            # Compute exponential backoff with jitter
            backoff_delay = BASE_DELAY * (2**attempt) + random.uniform(0, 0.5)

            # Use the smaller of the two values
            delay = min(backoff_delay, MAX_RETRY_TIME)

            if attempt == MAX_RETRIES - 1:
                raise

            logger.warning(
                f"Rate limit or transient error (HTTP {status_code}), "
                f"retrying in {delay:.2f}s (attempt {attempt + 1}/{MAX_RETRIES})..."
            )

            await asyncio.sleep(delay)
        except Exception:
            raise


@app.post("/embedding")
async def embed(
    req: EmbeddingRequest, client: AsyncAzureOpenAI = Depends(get_client)
) -> EmbeddingResponse:
    logger.info(
        f"Embedding request received for model: {req.deployment}, for {len(req.texts)} texts."
    )
    response = await with_backoff(
        client.embeddings.create,
        input=req.texts,
        model=req.deployment,
    )
    return EmbeddingResponse(
        embeddings=[item.embedding for item in response.data],
        model=response.model,
        usage=response.usage,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
