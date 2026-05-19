#!/usr/bin/env bash
# Symlink every skill under ai/skills/ into ~/.claude/skills/.
# Idempotent: re-running is a no-op when links are already correct.

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
SKILLS_SRC="$SCRIPT_DIR/skills"
SKILLS_DST="${CLAUDE_HOME:-$HOME/.claude}/skills"

mkdir -p "$SKILLS_DST"

for src in "$SKILLS_SRC"/*/; do
  name=$(basename "$src")
  dst="$SKILLS_DST/$name"
  src_abs=${src%/}

  if [[ -L "$dst" ]]; then
    if [[ "$(readlink "$dst")" == "$src_abs" ]]; then
      echo "= $name (already linked)"
      continue
    fi
    ln -sfn "$src_abs" "$dst"
    echo "~ $name (relinked)"
  elif [[ -e "$dst" ]]; then
    echo "! $name: real file/dir exists at $dst — skipping (move or remove it first)" >&2
  else
    ln -s "$src_abs" "$dst"
    echo "+ $name (linked)"
  fi
done
