FROM python:3.11-slim
WORKDIR /app

# Install Python dependencies
COPY agent_pool/agents/store_vectors/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the base server and agent code
COPY agent_pool/base_agent_server.py agent_pool/base_agent_server.py
COPY agent_pool/base_vector_db.py agent_pool/base_vector_db.py
COPY agent_pool/agents/store_vectors/ agent_pool/agents/store_vectors/

ENV PYTHONPATH=/app

WORKDIR /app/agent_pool/agents/store_vectors

CMD ["python", "agent.py"]

