FROM python:3.11-slim
WORKDIR /app

RUN apt-get update
RUN apt-get install -y libgl1-mesa-glx
RUN apt-get install -y libglib2.0-0
RUN apt-get install -y poppler-utils
RUN apt-get install -y tesseract-ocr-all 

COPY agent_pool/agents/file_to_text/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent_pool/base_agent_server.py agent_pool/base_agent_server.py

COPY agent_pool/agents/file_to_text/ agent_pool/agents/file_to_text/

ENV PYTHONPATH=/app
ENV OCR_AGENT=tesseract

WORKDIR /app/agent_pool/agents/file_to_text

CMD ["python", "agent.py"]

