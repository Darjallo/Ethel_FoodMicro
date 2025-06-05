FROM python:3.11-slim
WORKDIR /app

COPY agent_pool/agents/chunk_text/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent_pool/base_agent_server.py agent_pool/base_agent_server.py
COPY agent_pool/agents/chunk_text/ agent_pool/agents/chunk_text/

ENV PYTHONPATH=/app

WORKDIR /app/agent_pool/agents/chunk_text
CMD ["python", "agent.py"]

