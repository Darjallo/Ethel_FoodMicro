# Start from a minimal Debian image
FROM debian:bookworm-slim

# Create an unprivileged group & user with explicit UID:GID=1000
RUN groupadd --gid 1000 agentgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin agentuser

# Install Maxima (no extra packages required)
RUN apt-get update && \
    apt-get install -y --no-install-recommends maxima && \
    rm -rf /var/lib/apt/lists/*

# Switch to the unprivileged user
USER agentuser

# Set working directory inside the container
WORKDIR /home/agentuser

# No ENTRYPOINT or CMD—generic agent will invoke:
#   docker run --rm ... maxima --very-quiet --batch-string "<script>"
ENTRYPOINT []
