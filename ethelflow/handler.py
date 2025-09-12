from types import ModuleType
from fastapi.responses import StreamingResponse
# from ethelflow.flows.flow_resume import save_run
# import uuid


async def handler(
    mod: ModuleType, context: dict, query: dict, file_id: str, flow_name: str
):
    gen = mod.run(context=context, query=query, file_id=file_id, stream=False)

    first = await anext(gen, {})

    # if first.get("pause"):
    #     run_id = str(uuid.uuid4())
    #     save_run(run_id, flow_name, first["state"], first["next_node"])
    #     body_dict = {k: v for k, v in first.items() if k != "state"}
    #     body_dict.update({"info": "paused", "run_id": run_id})
    # else:
    #     body_dict = first

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
            # if update.get("pause"):
            #     save_run(run_id, flow_name, update["state"], update["next_node"])
            #     pause_payload = {k: v for k, v in update.items() if k != "state"}
            #     pause_payload.update({"info": "paused", "run_id": run_id})
            #     yield f"{pause_payload}\n"
            #     return

            yield f"{update}\n"

    return StreamingResponse(stream(), media_type="application/json")
