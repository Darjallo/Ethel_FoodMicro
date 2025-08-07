from pydantic import BaseModel


class ExecutionRequest(BaseModel):
    image: str
    filename: str
    code_b64: str


class ExecutionResult(BaseModel):
    return_code: int
    stdout: str
    stderr: str
