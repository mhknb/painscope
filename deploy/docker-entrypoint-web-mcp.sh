#!/bin/sh
set -eu

# Default container behavior: MCP + web UI (matches docker-compose intent).
# If arguments are passed (e.g. `docker run ... painscope scan ...`), delegate to the CLI.
if [ "$#" -gt 0 ]; then
  exec painscope "$@"
fi

painscope mcp-serve --host 0.0.0.0 --port 8765 &
exec painscope web-serve --host 0.0.0.0 --port 8787
