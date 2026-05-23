# Multi-process MCP stack: Python (uv), Node (npx), nginx ingress on 8080.
# Atlassian MCP (docker run) is excluded via mcp_servers.container.json baked as mcp_servers.json.
# Process tree: CMD → docker-entrypoint.sh → supervisord → [python main.py | nginx]
# main.py is the only app orchestrator (starts Streamlit, FastAPI client, Slack listener, etc.).
FROM python:3.12-bookworm

LABEL org.opencontainers.image.title="verna-mcp"
LABEL verna.entrypoint="main.py"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TERM=dumb \
    UV_NO_PROGRESS=1 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    NPM_CONFIG_CACHE=/tmp/npm-cache \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx supervisor curl ca-certificates libmagic1 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Frozen list from scripts/export-requirements.ps1 (uv pip freeze). Use uv pip sync so resolution matches uv, not pip.
COPY requirements.txt .
RUN pip install -q --upgrade pip uv \
    && uv pip sync --system --break-system-packages --no-cache -q requirements.txt

COPY . .
COPY Servers/config/mcp_servers.container.json Servers/config/mcp_servers.json

COPY deploy/azure/nginx.conf /etc/nginx/nginx.conf
RUN rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

COPY deploy/azure/supervisord.conf /etc/supervisor/conf.d/verna.conf

RUN sed -i 's/\r$//' /app/deploy/azure/docker-entrypoint.sh && chmod +x /app/deploy/azure/docker-entrypoint.sh

EXPOSE 8080

CMD ["/app/deploy/azure/docker-entrypoint.sh"]
