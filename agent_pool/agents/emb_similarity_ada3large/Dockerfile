FROM python:3.11-slim

# 1) Set workdir
WORKDIR /app

# 2) Install just pip‐side dependencies
COPY agent_pool/agents/emb_similarity_ada3large/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) Copy shared base modules and this agent’s files
COPY agent_pool/base_agent_server.py     agent_pool/base_agent_server.py
COPY agent_pool/base_vector_db.py         agent_pool/base_vector_db.py
COPY agent_pool/agents/emb_similarity_ada3large/ \
                                       agent_pool/agents/emb_similarity_ada3large/

# 4) Ensure Python can find our “agent_pool” package
ENV PYTHONPATH=/app

# 5) Switch into the agent’s folder and run it
WORKDIR /app/agent_pool/agents/emb_similarity_ada3large
CMD ["python", "agent.py"]

