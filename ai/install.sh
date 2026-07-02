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

# Symlink hook scripts under ai/hooks/ into ~/.claude/hooks/.
# Same link semantics as skills; an existing real file is backed up once.
HOOKS_SRC="$SCRIPT_DIR/hooks"
HOOKS_DST="${CLAUDE_HOME:-$HOME/.claude}/hooks"

mkdir -p "$HOOKS_DST"

for src in "$HOOKS_SRC"/*; do
  [[ -e "$src" ]] || continue
  name=$(basename "$src")
  dst="$HOOKS_DST/$name"

  if [[ -L "$dst" ]]; then
    if [[ "$(readlink "$dst")" == "$src" ]]; then
      echo "= hooks/$name (already linked)"
      continue
    fi
    ln -sfn "$src" "$dst"
    echo "~ hooks/$name (relinked)"
  elif [[ -e "$dst" ]]; then
    backup="$dst.pre-dotfiles.bak"
    [[ -e "$backup" ]] || cp "$dst" "$backup"
    ln -sfn "$src" "$dst"
    echo "~ hooks/$name (migrated real file → symlink; backup at $backup)"
  else
    ln -s "$src" "$dst"
    echo "+ hooks/$name (linked)"
  fi
done

# Seed ~/.claude/settings.json on a fresh machine. Copy, NOT symlink — the
# harness rewrites this file atomically (write temp + rename), which would
# sever a symlink on the first settings change. Local file wins after seeding.
SETTINGS_SRC="$SCRIPT_DIR/claude-settings.json"
SETTINGS_DST="${CLAUDE_HOME:-$HOME/.claude}/settings.json"

if [[ ! -e "$SETTINGS_DST" ]]; then
  cp "$SETTINGS_SRC" "$SETTINGS_DST"
  echo "+ settings.json (seeded — its hooks reference catnip and peon-ping; install those separately)"
elif ! diff -q "$SETTINGS_SRC" "$SETTINGS_DST" >/dev/null 2>&1; then
  echo "≠ settings.json drifted from ai/claude-settings.json (local wins; diff them to reconcile)"
else
  echo "= settings.json (matches template)"
fi

# Symlink the global CLAUDE.md — dotfiles is the source of truth.
# An existing real file is backed up once, then replaced with the symlink.
CLAUDE_SRC="$SCRIPT_DIR/CLAUDE.md"
CLAUDE_DST="${CLAUDE_HOME:-$HOME/.claude}/CLAUDE.md"

if [[ -L "$CLAUDE_DST" ]]; then
  if [[ "$(readlink "$CLAUDE_DST")" == "$CLAUDE_SRC" ]]; then
    echo "= CLAUDE.md (already linked)"
  else
    ln -sfn "$CLAUDE_SRC" "$CLAUDE_DST"
    echo "~ CLAUDE.md (relinked)"
  fi
elif [[ -e "$CLAUDE_DST" ]]; then
  backup="$CLAUDE_DST.pre-dotfiles.bak"
  [[ -e "$backup" ]] || cp "$CLAUDE_DST" "$backup"
  ln -sfn "$CLAUDE_SRC" "$CLAUDE_DST"
  echo "~ CLAUDE.md (migrated real file → symlink; backup at $backup)"
else
  ln -s "$CLAUDE_SRC" "$CLAUDE_DST"
  echo "+ CLAUDE.md (linked)"
fi
