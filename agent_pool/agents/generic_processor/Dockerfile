FROM python:3.11-slim

# Create group and unprivileged user with explicit UID:GID 1000
RUN groupadd --gid 1000 agentgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin agentuser

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY agent_pool/agents/generic_processor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy base server and agent code
COPY agent_pool/base_agent_server.py agent_pool/base_agent_server.py
COPY agent_pool/agents/generic_processor/ agent_pool/agents/generic_processor/

# Fix permissions
RUN chown -R agentuser:agentgroup /app

# Switch to unprivileged user
USER agentuser

# Expose listening port
EXPOSE 8000

# Configure Python path and start agent
ENV PYTHONPATH=/app
WORKDIR /app/agent_pool/agents/generic_processor
CMD ["python", "agent.py"]
