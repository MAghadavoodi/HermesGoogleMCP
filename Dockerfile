FROM ubuntu:24.04

# Install Node.js 22 and python3
RUN apt-get update && apt-get install -y curl python3 ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g @googleworkspace/cli && \
    rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy server files
COPY src/ ./src/

# Create workspace directories
RUN mkdir -p /workspace/google_mcp/{drive,gmail,calendar} && \
    mkdir -p /root/.config/gws

# Setup gws env
ENV GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file

# Create entrypoint
RUN echo '#!/bin/bash\n\
export GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file\n\
mkdir -p /root/.config/gws\n\
exec python3 /app/src/http_server.py' > /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8777
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8777/mcp || exit 1
ENTRYPOINT ["/entrypoint.sh"]
