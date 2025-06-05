FROM python:3.11-slim

WORKDIR /app

COPY flow_manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY flow_manager/flow_manager.py flow_manager.py
COPY flow_manager/asset_handler.py asset_handler.py
COPY flow_manager/flows flows

COPY ../agent_pool/agents/__init__.py agent_pool/agents/__init__.py

COPY ../agent_pool/agents/emb_file_ada3large/node_adapter.py agent_pool/agents/emb_file_ada3large/node_adapter.py
COPY ../agent_pool/agents/chunk_text/node_adapter.py agent_pool/agents/chunk_text/node_adapter.py
COPY ../agent_pool/agents/emb_similarity_ada3large/node_adapter.py agent_pool/agents/emb_similarity_ada3large/node_adapter.py
COPY ../agent_pool/agents/test_agent/node_adapter.py agent_pool/agents/test_agent/node_adapter.py
COPY ../agent_pool/agents/file_to_text/node_adapter.py agent_pool/agents/file_to_text/node_adapter.py
COPY ../agent_pool/agents/emb_ada3large/node_adapter.py agent_pool/agents/emb_ada3large/node_adapter.py
COPY ../agent_pool/agents/store_vectors/node_adapter.py agent_pool/agents/store_vectors/node_adapter.py

EXPOSE 8000
CMD ["python", "flow_manager.py"]
