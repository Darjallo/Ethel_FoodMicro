from typing import Any, Callable, Dict, AsyncGenerator
from ethelflow.agents.reasoning.models import ReasoningRequest, ReasoningResponse
import uuid
import aiohttp

REASONING_URL: str = "http://reasoning.default.svc:8000/reasoning"


def reasoning_node(
    document_id_key: str = "document_id",
    content_type_key: str = "content_type",
    prompt_key: str = "prompt",
    reasoning_effort_key: str = "reasoning_effort",
    stream_key: str = "stream",
    output_key: str = "reasoning_response",
) -> Callable[[Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
    async def node(state: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        document_id = state.get(document_id_key)
        content_type = state.get(content_type_key)
        prompt = state.get(prompt_key)
        reasoning_effort = state.get(reasoning_effort_key)
        stream = state.get(stream_key, False)

        if not isinstance(document_id, uuid.UUID):
            raise ValueError(
                f"Expected uuid.UUID for {document_id_key}, got {type(document_id)}"
            )
        if not isinstance(content_type, str):
            raise ValueError(
                f"Expected string for {content_type_key}, got {type(content_type)}"
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
            request = ReasoningRequest(
                document_id=document_id,
                content_type=content_type,
                prompt=prompt,
                reasoning_effort=reasoning_effort,
                stream=stream,
            )

            async with session.post(
                REASONING_URL, json=request.model_dump(mode="json"), timeout=300
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
                else:
                    response_data = await response.json()
                    data = ReasoningResponse.model_validate(response_data)
                    yield {output_key: data.response}

    return node
