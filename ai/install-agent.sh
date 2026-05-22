#!/usr/bin/env bash
# Full setup for the autonomous pipeline agent macOS user.
# Run as the 'agent' user after Claude Code and gh CLI are authenticated.
#
# Usage: bash install-agent.sh [--skip-plugins] [--skip-mcps] [--skip-proof-capture]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKIP_PLUGINS=false; SKIP_MCPS=false; SKIP_PROOF_CAPTURE=false

for arg in "$@"; do
  case "$arg" in
    --skip-plugins)       SKIP_PLUGINS=true ;;
    --skip-mcps)          SKIP_MCPS=true ;;
    --skip-proof-capture) SKIP_PROOF_CAPTURE=true ;;
  esac
done

step() { printf '\n\033[1;34m══ %s ══\033[0m\n' "$*"; }
green() { printf '\033[0;32m✓ %s\033[0m\n' "$*"; }

# ── Skills (symlinks into ~/.claude/skills/) ───────────────────────────────────
step "Skills"
bash "$SCRIPT_DIR/install.sh"

# ── Claude Code plugins (Superpowers, honcho) ──────────────────────────────────
step "Claude Code plugins"
if [[ "$SKIP_PLUGINS" == false ]]; then
  bash "$SCRIPT_DIR/scripts/install-claude-plugins.sh"
else
  echo "Skipped."
fi

# ── MCP configuration ──────────────────────────────────────────────────────────
step "MCP servers"
if [[ "$SKIP_MCPS" == false ]]; then
  bash "$SCRIPT_DIR/scripts/install-mcps.sh"
else
  echo "Skipped."
fi

# ── proof-capture tool ─────────────────────────────────────────────────────────
step "proof-capture"
if [[ "$SKIP_PROOF_CAPTURE" == false ]]; then
  bash "$SCRIPT_DIR/tools/proof-capture/install.sh"
else
  echo "Skipped."
fi

# ── Work directory structure ───────────────────────────────────────────────────
step "Work directories"
mkdir -p "$HOME/work/inputs" "$HOME/work/outputs" "$HOME/work/posthog-repo/worktrees"
green "~/work/ ready"

# ── PATH ───────────────────────────────────────────────────────────────────────
step "PATH"
for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
  if [[ -f "$rc" ]] && ! grep -q 'proof-capture' "$rc" 2>/dev/null; then
    printf '\nexport PATH="$HOME/bin:$PATH"  # proof-capture\n' >> "$rc"
    green "Added ~/bin to PATH in $rc"
  fi
done

printf '\n\033[0;32m✅ Agent install complete.\033[0m\n'
printf 'Run PREFLIGHT.sh to verify everything is wired correctly.\n\n'
