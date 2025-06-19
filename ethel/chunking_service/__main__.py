from fastapi import FastAPI
from ethel.chunking_service.models import ChunkingRequest
from pyethel.chunking.text_splitter import TextSplitter

app = FastAPI()


@app.get("/ping")
async def ping():
    return {"message": "pong"}


# create a /split_text endpoint that accepts POST requests with a JSON body
# example curl command:
# curl -X POST "http://localhost:8000/split_text" -H "Content-Type: application/json" -d '{"text": "This is a sample text to be split into chunks.", "chunk_size": 20, "chunk_overlap": 10}'
@app.post("/split_text")
async def split_text(req: ChunkingRequest):
    splitter = TextSplitter(chunk_size=20, chunk_overlap=10)

    chunks = splitter.split_text(req.text)

    return {"chunks": chunks}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
