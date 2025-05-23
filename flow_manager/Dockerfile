FROM python:3.11-slim

WORKDIR /app

COPY flow_manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ../agent_pool/agents/test_agent/node_adapter.py agent_pool/agents/test_agent/node_adapter.py

EXPOSE 8000
CMD ["python", "flow_manager.py"]
