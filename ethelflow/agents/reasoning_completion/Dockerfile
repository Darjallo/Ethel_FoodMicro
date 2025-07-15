FROM python:3.11-slim
WORKDIR /app

# Install gridfs prerequisites (if any)
# (no extra OS packages needed beyond python)

# Copy and install Python dependencies
COPY agent_pool/agents/reasoning_completion/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the base server machinery
COPY agent_pool/base_agent_server.py agent_pool/base_agent_server.py

# Copy this agent’s code
COPY agent_pool/agents/reasoning_completion/ agent_pool/agents/reasoning_completion/

ENV PYTHONPATH=/app

WORKDIR /app/agent_pool/agents/reasoning_completion
CMD ["python", "agent.py"]

