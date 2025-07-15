# agent_pool/agents/generic_processor/Dockerfile
FROM python:3.11-slim

# ——— 1) Create agentuser (UID:GID=1000) ————————————————
RUN groupadd --gid 1000 agentgroup \
 && useradd --uid 1000 --gid 1000 \
           --create-home --shell /usr/sbin/nologin agentuser

# ——— 2) Docker socket group at build-time ——————————————
ARG DOCKER_GID
# Create (or reuse) a group with that GID, and add agentuser to it
RUN groupadd --gid ${DOCKER_GID} dockerhost \
 && usermod -aG dockerhost agentuser

# ——— 3) Install Docker CLI (so we can spawn containers) —————
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends docker.io \
 && rm -rf /var/lib/apt/lists/*

# ——— 4) Install Python requirements ————————————————
WORKDIR /app
COPY agent_pool/agents/generic_processor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ——— 5) Copy in server & agent code ————————————————
COPY agent_pool/base_agent_server.py agent_pool/base_agent_server.py
COPY agent_pool/agents/generic_processor/ agent_pool/agents/generic_processor/

# ——— 6) Fix permissions on /app ——————————————————————
RUN chown -R agentuser:agentgroup /app

# ——— 7) Drop to unprivileged user ————————————————————
USER agentuser

# ——— 8) Expose port & start the agent ——————————————————
EXPOSE 8000
ENV PYTHONPATH=/app
WORKDIR /app/agent_pool/agents/generic_processor
CMD ["python", "agent.py"]

