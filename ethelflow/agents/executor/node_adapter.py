from typing import Callable, Dict, Any, AsyncGenerator
from ethelflow.agents.executor.models import ExecutionRequest, ExecutionResult
import aiohttp
import base64

# could also be an environment variable
EXECUTOR_URL: str = "http://executor.default.svc:8000/execute"


def executor_node(
    image_key: str = "image",
    code_key: str = "code",
    output_key: str = "execution_result",
) -> Callable[[Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
    async def node(state: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        # 1) Fetch image and code from state
        image = state.get(image_key)
        if not isinstance(image, str):
            raise ValueError(f"Expected a string for {image_key}, got {type(image)}")

        code = state.get(code_key)
        if not isinstance(code, str):
            raise ValueError(f"Expected a string for {code_key}, got {type(code)}")

        # 2) Build payload and POST to the running executor agent
        code_b64 = base64.b64encode(code.encode("utf-8")).decode("utf-8")
        request = ExecutionRequest(
            image=image,
            code_b64=code_b64,
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(
                EXECUTOR_URL, json=request.model_dump(), timeout=60
            ) as response:
                if response.status != 200:
                    error_detail = await response.text()
                    raise ValueError(
                        f"Executor service returned status {response.status}: {error_detail}"
                    )
                response_data = await response.json()

                data = ExecutionResult.model_validate(response_data)

        yield {output_key: data}

    return node
