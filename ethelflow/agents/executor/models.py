from pydantic import BaseModel
from uuid import UUID


class ExecutionRequest(BaseModel):
    image: str
    code_b64: str
    # possible other fields:
    # command: controls the command to run in the container
    # type: Python, R, Maxima, etc.
    # deadline: in seconds, for the execution
    # resources: CPU, memory limits, etc.


class ExecutionResult(BaseModel):
    execution_id: UUID
    return_code: int
    stdout: str
    stderr: str
