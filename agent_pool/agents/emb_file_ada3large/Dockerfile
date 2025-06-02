FROM python:3.11-slim
WORKDIR /app

COPY agent_pool/agents/emb_file_ada3large/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent_pool/base_agent_server.py agent_pool/base_agent_server.py
COPY agent_pool/agents/emb_file_ada3large/ agent_pool/agents/emb_file_ada3large/

ENV PYTHONPATH=/app

WORKDIR /app/agent_pool/agents/emb_file_ada3large

CMD ["python", "agent.py"]

