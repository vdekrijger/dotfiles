#!/usr/bin/env bash
# Configures ~/.claude/mcp.json for the agent user's claude -p sessions.
# Merges into existing config — safe to re-run.
#
# Reads from ~/work/config.env if present:
#   POSTHOG_API_KEY  personal API key
#   POSTHOG_HOST     instance URL (default: https://us.posthog.com)

set -euo pipefail

green() { printf '\033[0;32m  ✓ %s\033[0m\n' "$*"; }
warn()  { printf '\033[0;33m  ⚠ %s\033[0m\n' "$*"; }
info()  { printf '\033[0;34m  → %s\033[0m\n' "$*"; }

MCP_CONFIG="${CLAUDE_HOME:-$HOME/.claude}/mcp.json"
mkdir -p "$(dirname "$MCP_CONFIG")"

[[ -f "$HOME/work/config.env" ]] && source "$HOME/work/config.env"

POSTHOG_API_KEY="${POSTHOG_API_KEY:-REPLACE_ME}"
POSTHOG_HOST="${POSTHOG_HOST:-https://us.posthog.com}"

info "Writing MCP config to $MCP_CONFIG..."

python3 - "$MCP_CONFIG" "$POSTHOG_API_KEY" "$POSTHOG_HOST" << 'PYEOF'
import json, sys

config_path, posthog_key, posthog_host = sys.argv[1], sys.argv[2], sys.argv[3]

try:
    with open(config_path) as f:
        config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    config = {}

config.setdefault("mcpServers", {})

# PostHog MCP: query events, feature flags, insight definitions, schema
config["mcpServers"]["posthog"] = {
    "command": "npx",
    "args": ["-y", "@posthog/mcp-server"],
    "env": {"POSTHOG_API_KEY": posthog_key, "POSTHOG_HOST": posthog_host},
}

# Playwright MCP: agent-controlled browser during implementation and live verification.
# Note: proof-capture handles standardised artifact output separately.
config["mcpServers"]["playwright"] = {
    "command": "npx",
    "args": ["-y", "@playwright/mcp", "--headless"],
}

with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")

print(f"  Written {len(config['mcpServers'])} MCP server(s)")
PYEOF

green "MCP config written"

if grep -q "REPLACE_ME" "$MCP_CONFIG" 2>/dev/null; then
  warn "POSTHOG_API_KEY is REPLACE_ME — set it in ~/work/config.env and re-run"
fi

info "Pre-warming packages..."
npx --yes @posthog/mcp-server --help &>/dev/null && green "@posthog/mcp-server cached" || warn "@posthog/mcp-server pre-warm failed"
npx --yes @playwright/mcp --help &>/dev/null && green "@playwright/mcp cached" || warn "@playwright/mcp pre-warm failed"
