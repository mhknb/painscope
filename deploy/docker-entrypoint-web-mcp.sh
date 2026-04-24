#!/bin/sh
set -eu

# Default: MCP + web UI. Coolify sometimes passes a useless argv (e.g. a lone
# "painscope" command override); treat that like "no args" so we never hit Typer
# "Missing command." If real CLI args are present, delegate.
if [ "$#" -eq 0 ] || {
  [ "$#" -eq 1 ] && { [ "$1" = "painscope" ] || [ -z "$1" ]; }
}; then
  painscope mcp-serve --host 0.0.0.0 --port 8765 &
  exec painscope web-serve --host 0.0.0.0 --port 8787
fi

exec painscope "$@"
