# Start from official slim Python
FROM python:3.12-slim

# Create a dedicated group and unprivileged user with UID:GID=1000
RUN groupadd --gid 1000 agentgroup \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin agentuser

# Set working directory
WORKDIR /home/agentuser

# Copy Python dependencies definition
COPY agent_pool/agents/python_processor/requirements.txt .

# Install dependencies, no cache
RUN pip install --no-cache-dir -r requirements.txt

# Drop privileges
USER agentuser

# Default command is empty; generic processor will supply 'python -I -c <script>'
ENTRYPOINT []
