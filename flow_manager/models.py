from pydantic import BaseModel, Field, field_validator
from importlib.util import find_spec


class FlowRequest(BaseModel):
    """
    Represents a request to execute a flow.
    """

    flow: str = Field(..., description="The name of the flow to execute")
    tenant: str = Field(..., description="The tenant identifier for the flow execution")
    context: dict = Field(
        default_factory=dict, description="Context data for the flow execution"
    )
    flow_reload: bool = Field(
        False, description="Whether to reload the flow module before execution"
    )
    stream: bool = Field(False, description="Whether to stream the response")
    query: dict = Field(
        default_factory=dict, description="Query parameters for the flow execution"
    )
    file_id: str | None = Field(
        None, description="Optional file identifier for the flow execution"
    )

    @field_validator("flow")
    @classmethod
    def validate_flow_name(cls, v):
        """
        Validate that the flow name is a valid Python module name.
        """
        if not v or not find_spec(f"flows.{v}"):
            raise ValueError(f"No such flow '{v}'")
        return v
