#!/usr/bin/env bash
# deploy/vps-deploy.sh — Deploy painscope to Contabo VPS via Docker
#
# Usage:
#   ./deploy/vps-deploy.sh [VPS_HOST] [VPS_USER]
#
# Environment variables (optional overrides):
#   VPS_HOST  - VPS IP or hostname (default: 38.242.220.13)
#   VPS_USER  - SSH user (default: root)
#   VPS_PASS  - SSH password (will prompt if not set)
#   REMOTE_DIR - Remote directory (default: /root/painscope)
#   WEB_BIND_IP - Web UI bind address (default: 127.0.0.1)
#   MCP_HOST_PORT - Host port for MCP endpoint (default: 8767)

set -euo pipefail

VPS_HOST="${VPS_HOST:-38.242.220.13}"
VPS_USER="${VPS_USER:-root}"
REMOTE_DIR="${REMOTE_DIR:-/root/painscope}"
SSH_STRICT_HOST_KEY_CHECKING="${SSH_STRICT_HOST_KEY_CHECKING:-accept-new}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ── helpers ────────────────────────────────────────────────────────────────

log() { echo "[deploy] $*"; }

ssh_cmd() {
  if [[ -n "${VPS_PASS:-}" ]]; then
    sshpass -p "$VPS_PASS" ssh -o StrictHostKeyChecking="${SSH_STRICT_HOST_KEY_CHECKING}" "${VPS_USER}@${VPS_HOST}" "$@"
  else
    ssh -o StrictHostKeyChecking="${SSH_STRICT_HOST_KEY_CHECKING}" "${VPS_USER}@${VPS_HOST}" "$@"
  fi
}

scp_cmd() {
  if [[ -n "${VPS_PASS:-}" ]]; then
    sshpass -p "$VPS_PASS" scp -o StrictHostKeyChecking="${SSH_STRICT_HOST_KEY_CHECKING}" "$@"
  else
    scp -o StrictHostKeyChecking="${SSH_STRICT_HOST_KEY_CHECKING}" "$@"
  fi
}

env_value() {
  local key="$1"
  local value
  value="$(awk -F= -v key="$key" '$1 == key {print substr($0, length(key) + 2)}' "$PROJECT_DIR/.env" | tail -n 1)"
  value="${value%\"}"
  value="${value#\"}"
  echo "$value"
}

# ── 0. Pre-flight ──────────────────────────────────────────────────────────

log "Deploying painscope to ${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}"

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  log "ERROR: .env file not found at $PROJECT_DIR/.env"
  log "Copy .env.example to .env and fill in your API keys."
  exit 1
fi

WEB_BIND_IP="${WEB_BIND_IP:-$(env_value WEB_BIND_IP)}"
WEB_BIND_IP="${WEB_BIND_IP:-127.0.0.1}"
MCP_HOST_PORT="${MCP_HOST_PORT:-$(env_value MCP_HOST_PORT)}"
MCP_HOST_PORT="${MCP_HOST_PORT:-8767}"
WEB_PASSWORD="${PAINSCOPE_WEB_PASSWORD:-$(env_value PAINSCOPE_WEB_PASSWORD)}"

if [[ "$WEB_BIND_IP" != "127.0.0.1" && "$WEB_BIND_IP" != "localhost" && -z "$WEB_PASSWORD" ]]; then
  log "ERROR: WEB_BIND_IP=${WEB_BIND_IP} exposes the web UI beyond localhost, but PAINSCOPE_WEB_PASSWORD is empty."
  log "Set PAINSCOPE_WEB_PASSWORD in .env, or keep WEB_BIND_IP=127.0.0.1 and use an SSH tunnel."
  exit 1
fi

# ── 1. Create remote directory ─────────────────────────────────────────────

log "Creating remote directory..."
ssh_cmd "mkdir -p ${REMOTE_DIR}"

# ── 2. Upload files ────────────────────────────────────────────────────────

log "Uploading project files..."
scp_cmd -r \
  "$PROJECT_DIR/src" \
  "$PROJECT_DIR/Dockerfile" \
  "$PROJECT_DIR/docker-compose.yml" \
  "$PROJECT_DIR/pyproject.toml" \
  "$PROJECT_DIR/README.md" \
  "$PROJECT_DIR/.env" \
  "${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}/"

# ── 3. Build and restart ───────────────────────────────────────────────────

log "Building Docker image and restarting container..."
ssh_cmd "cd ${REMOTE_DIR} && docker compose build --no-cache && docker compose up -d"

# ── 4. Health check ────────────────────────────────────────────────────────

wait_for_health() {
  local container="$1"
  log "Waiting for ${container} to be healthy (up to 120s)..."
  for i in $(seq 1 24); do
    STATUS=$(ssh_cmd "docker inspect --format='{{.State.Health.Status}}' ${container} 2>/dev/null || echo 'starting'")
    if [[ "$STATUS" == "healthy" ]]; then
      log "${container} is healthy!"
      return 0
    fi
    log "  ${container}: $STATUS (attempt $i/24)"
    sleep 5
  done
  log "ERROR: ${container} did not report healthy within timeout."
  return 1
}

wait_for_health "painscope-mcp"

log "Deploy complete. MCP endpoint: http://${VPS_HOST}:${MCP_HOST_PORT}/mcp"
if [[ "$WEB_BIND_IP" == "127.0.0.1" || "$WEB_BIND_IP" == "localhost" ]]; then
  log "Web UI is bound to localhost on the VPS."
  log "Use: ssh -L 8787:127.0.0.1:8787 ${VPS_USER}@${VPS_HOST}"
  log "Then open: http://127.0.0.1:8787"
else
  log "Web UI: http://${VPS_HOST}:8787"
fi
log ""
log "To add to Hermes (~/.hermes/config.yaml):"
log "  mcp_servers:"
log "    painscope:"
log "      url: \"http://${VPS_HOST}:${MCP_HOST_PORT}/mcp\""
log "      enabled: true"
log "      timeout: 300"
