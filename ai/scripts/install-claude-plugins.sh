#!/usr/bin/env bash
# Installs Claude Code plugins for the autonomous pipeline agent user.
# Skills (review-swarm, proof-driven-dev, etc.) are handled by ai/install.sh
# via symlinks — this script handles plugins that need a separate install step.

set -euo pipefail

green() { printf '\033[0;32m  ✓ %s\033[0m\n' "$*"; }
warn()  { printf '\033[0;33m  ⚠ %s\033[0m\n' "$*"; }
info()  { printf '\033[0;34m  → %s\033[0m\n' "$*"; }

plugin_installed() { claude code plugins list 2>/dev/null | grep -qi "$1"; }

# ── Superpowers ────────────────────────────────────────────────────────────────
# Provides: brainstorm, subagent-driven-dev, TDD, writing-plans, code-reviewer
# Required by: proof-driven-dev pipeline (phases 2, 5)

info "Superpowers..."
if plugin_installed "superpowers"; then
  green "Already installed"
else
  if claude code plugins install superpowers@claude-plugins-official --global 2>/dev/null; then
    green "Installed via official marketplace"
  else
    warn "Marketplace failed — trying skill install..."
    claude skill install superpowers --global 2>/dev/null \
      && green "Installed via skill install" \
      || warn "Failed — install manually inside Claude Code: /plugin install superpowers@claude-plugins-official"
  fi
fi

# ── Honcho integration ─────────────────────────────────────────────────────────
# Useful when the agent writes code that itself needs Honcho memory wiring.
# Not required for pipeline operation but handy for meta-work.

info "honcho-integration skill..."
if claude skill list 2>/dev/null | grep -qi honcho; then
  green "Already installed"
else
  npx --yes skills add plastic-labs/honcho 2>/dev/null \
    && green "Installed" \
    || warn "Failed — run: npx skills add plastic-labs/honcho"
fi

printf '\n'
info "Installed plugins:"
claude code plugins list 2>/dev/null | grep -iE 'superpowers|honcho' || echo "  (none matched — check manually)"
