from types import ModuleType
from fastapi.responses import StreamingResponse


async def handler(
    mod: ModuleType, context: dict, query: dict, file_id: str, stream: bool
):
    if stream:

        async def stream():
            async for update in mod.run(
                context=context, query=query, file_id=file_id, stream=True
            ):
                yield update

        return StreamingResponse(stream(), media_type="application/json")
    else:
        gen = mod.run(context=context, query=query, file_id=file_id, stream=False)

        first = await anext(gen, {})

        return first


def handler_stream(
    mod: ModuleType, context: dict, query: dict, file_id: str, flow_name: str
) -> StreamingResponse:
    """
    Handle streaming response for flow execution.
    """

    def stream():
        # run_id = str(uuid.uuid4())
        for update in mod.run(
            context=context, query=query, file_id=file_id, stream=True
        ):
            yield f"{update}\n"

    return StreamingResponse(stream(), media_type="application/json")
