# Start from a minimal Debian image
FROM debian:bookworm-slim

# Create an unprivileged group & user with explicit UID:GID=1000
RUN groupadd --gid 1000 agentgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin agentuser

# Install Maxima and help system docs
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends maxima maxima-doc && \
    rm -rf /var/lib/apt/lists/*

# Switch to the unprivileged user and set working directory
USER agentuser
WORKDIR /home/agentuser /home/agentuser

# No ENTRYPOINT or CMD—generic agent will invoke:
#   docker run --rm ... maxima --very-quiet --batch-string "<script>"
