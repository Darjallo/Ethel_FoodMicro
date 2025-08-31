from fastapi import FastAPI, Depends, HTTPException
from sqlmodel import Session, select, create_engine
from ethelflow.agents.file_to_text.models import FileToTextRequest, FileToTextResponse
from ethelflow.data.models import EthelDocument
from ethelflow.settings.postgres_settings import postgres_settings
from ethelflow.assets.s3 import s3_manager
from pypdf import PdfReader
import io

engine = create_engine(postgres_settings.url)


def get_session():
    with Session(engine) as session:
        yield session


app = FastAPI()


@app.post("/file_to_text", response_model=FileToTextResponse)
async def file_to_text(req: FileToTextRequest, session: Session = Depends(get_session)):
    statement = select(EthelDocument).where(EthelDocument.id == req.document_id)
    document = session.exec(statement).one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.content_type != "application/pdf":
        raise HTTPException(
            status_code=400, detail="Only PDF files are supported at the moment."
        )

    try:
        file_object = io.BytesIO()
        s3_manager.download_file(str(document.id), file_object)
        file_object.seek(0)

        reader = PdfReader(file_object)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""

        return FileToTextResponse(text=text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
