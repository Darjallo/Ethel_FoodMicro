from typing import Literal
from pydantic import BaseModel, model_validator
from uuid import UUID


class ExecutionRequest(BaseModel):
    image: str
    type: Literal["python", "r", "maxima"]
    # code_b64 required if type is python or r
    code_b64: str | None = None
    # expr is required if type is maxima
    expr: str | None = None
    # possible other fields:
    # command: controls the command to run in the container
    # type: Python, R, Maxima, etc.
    # deadline: in seconds, for the execution
    # resources: CPU, memory limits, etc.

    @model_validator(mode="after")
    def validate(self):
        if self.type in ["python", "r"] and not self.code_b64:
            raise ValueError("code_b64 is required for python and r types")
        if self.type == "maxima" and not self.expr:
            raise ValueError("expr is required for maxima type")
        return self


class ExecutionResult(BaseModel):
    execution_id: UUID
    return_code: int
    stdout: str
    stderr: str
