from types import ModuleType
from fastapi.responses import StreamingResponse
import uuid


async def handler(
    mod: ModuleType,
    context: dict,
    query: dict,
    file_id: str,
    stream: bool,
    checkpointer=None,
    thread_id: uuid.UUID = uuid.uuid4(),
):
    if stream:

        async def stream():
            async for update in mod.run(
                thread_id=thread_id,
                context=context,
                query=query,
                file_id=file_id,
                stream=True,
                checkpointer=checkpointer,
            ):
                yield update

        return StreamingResponse(stream(), media_type="application/json")
    else:
        gen = mod.run(
            thread_id=thread_id,
            context=context,
            query=query,
            file_id=file_id,
            stream=False,
            checkpointer=checkpointer,
        )

        first = await anext(gen, {})

        return first
