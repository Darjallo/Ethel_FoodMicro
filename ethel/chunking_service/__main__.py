from fastapi import FastAPI
from pydantic import BaseModel, field_validator, model_validator
from pyethel.chunking.text_splitter import TextSplitter

app = FastAPI()


@app.get("/ping")
async def ping():
    """
    A simple health check endpoint.
    """
    return {"message": "pong"}


class ChunkingRequest(BaseModel):
    """
    Request model for the split_text endpoint.

    :param text: The text to be split.
    """

    text: str
    chunk_size: int
    chunk_overlap: int

    @field_validator("chunk_size", "chunk_overlap")
    @classmethod
    def validate_positive(cls, v):
        """
        Validate that chunk_size and chunk_overlap are positive integers.
        """
        if v <= 0:
            raise ValueError("Value must be greater than 0")
        return v

    @model_validator(mode="after")
    def validate_chunk_overlap(self):
        """
        Validate that chunk_overlap is less than chunk_size.
        """
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return self


# create a /split_text endpoint that accepts POST requests with a JSON body
# example curl command:
# curl -X POST "http://localhost:8000/split_text" -H "Content-Type: application/json" -d '{"text": "This is a sample text to be split into chunks.", "chunk_size": 20, "chunk_overlap": 10}'
@app.post("/split_text")
async def split_text(req: ChunkingRequest):
    """
    Endpoint to split text into chunks.

    :param text: The text to be split.
    :return: A list of text chunks.
    """
    # # Create an instance of TextSplitter with default parameters
    splitter = TextSplitter(chunk_size=20, chunk_overlap=10)

    # # Split the provided text
    chunks = splitter.split_text(req.text)

    return {"chunks": chunks}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
