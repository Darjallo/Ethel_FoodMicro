from pydantic import BaseModel, Field, field_validator
from importlib.util import find_spec
from typing import Any
from uuid import UUID


class FlowRequest(BaseModel):
    """
    Represents a request to execute a flow.
    """

    flow: str = Field(..., description="The name of the flow to execute")
    tenant: str = Field(..., description="The tenant identifier for the flow execution")
    context: dict = Field(
        default_factory=dict, description="Context data for the flow execution"
    )
    stream: bool = Field(False, description="Whether to stream the response")

    @field_validator("flow")
    @classmethod
    def validate_flow_name(cls, v):
        """
        Validate that the flow name is a valid Python module name.
        """
        if not v or not find_spec(f"ethelflow.flows.{v}"):
            raise ValueError(f"No such flow '{v}'")
        return v


class FlowContinueRequest(BaseModel):
    """
    Represents a request to continue a LangGraph flow that has been interrupted.
    The continuation request must include a list of mappings from interrupt IDs to values.
    """

    data: dict[str, Any] = Field(
        ..., description="Mapping from interrupt IDs to values"
    )
    stream: bool = Field(False, description="Whether to stream the response")

    # TODO: validate that the interrupt IDs are valid UUIDs
