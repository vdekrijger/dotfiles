#!/usr/bin/env bash
set -euo pipefail

# Setup script for the pattern-eval Claude Code skill.
# Creates required directory structure and seed files.
#
# Usage:
#   bash ~/.claude/skills/pattern-eval/setup.sh

PATTERNS_DIR="$HOME/.claude/power-user/patterns"

echo "Setting up pattern-eval..."

# Create directory structure
mkdir -p "$PATTERNS_DIR/evaluations"

# Seed trends.md if it doesn't exist
if [ ! -f "$PATTERNS_DIR/trends.md" ]; then
  cat > "$PATTERNS_DIR/trends.md" << 'EOF'
# Pattern Evaluation Trends

| Week | One-shot rate | Avg exchanges | Corrections | Top anti-pattern |
|------|--------------|---------------|-------------|------------------|
EOF
  echo "  Created trends.md"
else
  echo "  trends.md already exists, skipping"
fi

# Seed proposed-changes.md if it doesn't exist
if [ ! -f "$PATTERNS_DIR/proposed-changes.md" ]; then
  cat > "$PATTERNS_DIR/proposed-changes.md" << 'EOF'
# Proposed Changes Log

Track all proposed CLAUDE.md/memory/skill changes from pattern evaluations.

| Date | Proposal | Status | Rationale |
|------|----------|--------|-----------|
EOF
  echo "  Created proposed-changes.md"
else
  echo "  proposed-changes.md already exists, skipping"
fi

echo ""
echo "Done. Run /pattern-eval in Claude Code to start your first evaluation."
echo ""
echo "Optional: install the weekly launchd schedule with:"
echo "  bash ~/.claude/skills/pattern-eval/install-schedule.sh"
