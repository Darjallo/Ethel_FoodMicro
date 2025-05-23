FROM python:3.11-slim
WORKDIR /app

COPY agent_pool/base_agent_server.py agent_pool/base_agent_server.py
COPY agent_pool/agents/test_agent/ agent_pool/agents/test_agent/

WORKDIR /app/agent_pool/agents/test_agent

CMD ["python", "agent.py"]

