from fastapi import FastAPI, HTTPException
from flow_resume import runs
from flow_manager.models import FlowRequest
from flow_manager.handler import handler, handler_stream
import sys
import importlib

app = FastAPI()


# an endpoint to get the "run" with a specific id (GET /run/{run_id})
@app.get("/flow/{run_id}")
async def get_run(run_id: str):
    doc = runs.find_one({"_id": run_id}, projection={"state": False})
    if not doc:  # return 404 if run not found
        raise HTTPException(status_code=404, detail="Run not found")

    return doc


@app.post("/flow")
async def create_flow(flow_request: FlowRequest):
    """
    Endpoint to create a flow execution request.
    """
    if flow_request.flow_reload:
        sys.modules.pop(f"flows.{flow_request.flow}", None)
    mod = importlib.import_module(f"flows.{flow_request.flow}")

    if flow_request.stream:
        return handler_stream(
            mod,
            flow_request.context,
            flow_request.query,
            flow_request.file_id,
            flow_request.flow,
        )
    else:
        return handler(
            mod,
            flow_request.context,
            flow_request.query,
            flow_request.file_id,
            flow_request.flow,
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
