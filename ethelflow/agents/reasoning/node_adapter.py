from typing import Any, Callable, Dict, AsyncGenerator
from ethelflow.agents.reasoning.models import ReasoningRequest, ReasoningResponse
import uuid
import aiohttp

REASONING_URL: str = "http://reasoning.default.svc:8000/reasoning"
REASONING_WITH_DOCUMENT_URL: str = (
    "http://reasoning.default.svc:8000/reasoning_with_document"
)


def reasoning_node(
    deployment_key: str = "deployment",
    prompt_key: str = "prompt",
    stream_key: str = "stream",
    # Optional key for additional messages in the chat completion
    messages_key: str = "messages",
    # Optional key for reasoning effort
    reasoning_effort_key: str | None = None,
    # Optional keys if document is included in the prompt
    document_id_key: str | None = None,
    content_type_key: str | None = None,
    # Output key for the reasoning response
    output_key: str = "reasoning_response",
) -> Callable[[Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
    async def node(state: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        deployment = state.get(deployment_key)
        prompt = state.get(prompt_key)
        stream = state.get(stream_key, False)
        document_id = state.get(document_id_key) if document_id_key else None
        messages = state.get(messages_key) if messages_key else None
        content_type = state.get(content_type_key) if content_type_key else None
        reasoning_effort = (
            state.get(reasoning_effort_key) if reasoning_effort_key else None
        )

        if isinstance(document_id, uuid.UUID):
            # there is a document in the prompt
            if not isinstance(content_type, str):
                raise ValueError(
                    "content_type must be provided if document_id is provided"
                )
        elif document_id is not None:
            # document_id is provided but not a UUID
            raise ValueError(
                f"Expected UUID for {document_id_key}, got {type(document_id)}"
            )

        if not isinstance(prompt, str):
            raise ValueError(f"Expected string for {prompt_key}, got {type(prompt)}")

        if reasoning_effort is not None and reasoning_effort not in [
            "low",
            "medium",
            "high",
        ]:
            raise ValueError(
                f'Expected "low", "medium", or "high" for {reasoning_effort_key}, got {reasoning_effort}'
            )

        async with aiohttp.ClientSession() as session:
            if document_id:
                url = REASONING_WITH_DOCUMENT_URL
                request = ReasoningRequest(
                    deployment=deployment,
                    document_id=document_id,
                    content_type=content_type,
                    messages=messages,
                    prompt=prompt,
                    reasoning_effort=reasoning_effort,
                    stream=stream,
                )
            else:
                url = REASONING_URL
                request = ReasoningRequest(
                    deployment=deployment,
                    messages=messages,
                    prompt=prompt,
                    reasoning_effort=reasoning_effort,
                    stream=stream,
                )

            async with session.post(
                url, json=request.model_dump(mode="json"), timeout=300
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(
                        f"Reasoning service returned status {response.status}: {error_text}"
                    )

                if stream:
                    full_response = ""
                    async for chunk in response.content.iter_any():
                        chunk_text = chunk.decode("utf-8")
                        full_response += chunk_text
                        yield {output_key: chunk_text}

                    yield {output_key: "\n"}

                    yield {output_key: None}  # Indicate end of stream
                    yield {output_key: full_response}
                else:
                    response_data = await response.json()
                    data = ReasoningResponse.model_validate(response_data)
                    yield {output_key: data.response}

    return node
