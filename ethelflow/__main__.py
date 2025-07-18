from fastapi import FastAPI, HTTPException

from ethelflow.models import FlowRequest
from ethelflow.handler import handler, handler_stream
import sys
import importlib

from uuid import UUID

app = FastAPI()


# an endpoint to get the "run" with a specific id (GET /run/{run_id})
@app.get("/flow/{run_id}")
async def get_run(run_id: UUID):
    # doc = runs.find_one({"_id": run_id}, projection={"state": False})
    doc = None
    if not doc:  # return 404 if run not found
        raise HTTPException(status_code=404, detail="Run not found")

    return doc


@app.post("/flow")
async def create_flow(flow_request: FlowRequest):
    """
    Endpoint to create a flow execution request.
    """
    if flow_request.flow_reload:
        sys.modules.pop(f"ethelflow.flows.{flow_request.flow}", None)
    mod = importlib.import_module(f"ethelflow.flows.{flow_request.flow}")

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

    uvicorn.run(app, host="0.0.0.0", port=8080)
