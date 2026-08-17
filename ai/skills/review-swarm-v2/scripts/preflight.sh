#!/bin/bash
# review-swarm-v2 Stage A. Validates args, builds an isolated worktree, measures a gate baseline.
# Written for macOS bash 3.2, so no associative arrays and no mapfile.
set -uo pipefail

REPO="" BRANCH="" BASELINE="fast" WT_ROOT="${TMPDIR:-/tmp}"
WT_ROOT="${WT_ROOT%/}/rsv2"
GATES=""

die() { echo "[preflight] FAIL: $*" >&2; exit 1; }
say() { echo "[preflight] $*"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --repo) REPO="${2-}"; shift 2 ;;
        --branch) BRANCH="${2-}"; shift 2 ;;
        --baseline) BASELINE="${2-}"; shift 2 ;;
        --worktree-root) WT_ROOT="${2-}"; shift 2 ;;
        --gate) GATES="${GATES}${2-}"$'\n'; shift 2 ;;
        *) die "unknown argument: $1" ;;
    esac
done

# 1. Arg validation. Fail with the argument's name rather than dispatching an empty value.
[ -n "$REPO" ] || REPO="$(pwd)"
[ -d "$REPO" ] || die "--repo does not exist: $REPO"
REPO="$(cd "$REPO" && git rev-parse --show-toplevel 2>/dev/null)" || die "--repo is not a git repo"
[ -n "$BRANCH" ] || BRANCH="$(git -C "$REPO" rev-parse --abbrev-ref HEAD)"
[ -n "$BRANCH" ] || die "--branch is empty and HEAD is detached, so there is nothing to review"
git -C "$REPO" rev-parse --verify "$BRANCH" >/dev/null 2>&1 || die "--branch does not exist: $BRANCH"
case "$BASELINE" in full|fast|skip) ;; *) die "--baseline must be full, fast or skip (got: $BASELINE)" ;; esac

HEAD_SHA="$(git -C "$REPO" rev-parse "$BRANCH")"
SLUG="$(basename "$REPO" | tr -c '[:alnum:]' '-' | sed 's/-*$//')"

# 2. Worktree at an explicit absolute path. Detached, because $BRANCH is checked out in the main tree.
WT="$WT_ROOT/${SLUG}-$(echo "$BRANCH" | tr -c '[:alnum:]' '-' | sed 's/-*$//')-${HEAD_SHA:0:8}"
if [ -d "$WT" ]; then
    say "reusing existing worktree"
else
    mkdir -p "$WT_ROOT" || die "cannot create worktree root: $WT_ROOT"
    git -C "$REPO" worktree add --detach "$WT" "$BRANCH" >/dev/null 2>&1 || die "worktree add failed for $BRANCH"
fi
# Canonicalize before the self-check. On macOS $TMPDIR is under /var/folders, a symlink to
# /private/var/folders, and git reports the resolved path — an unresolved $WT never matches.
WT="$(cd "$WT" && pwd -P)"
say "WORKTREE=$WT"

# 3. Self-check. Everything downstream is pinned to this path.
ACTUAL="$(git -C "$WT" rev-parse --show-toplevel 2>/dev/null)"
[ "$ACTUAL" = "$WT" ] || die "worktree self-check failed: expected $WT, got ${ACTUAL:-<none>}"
say "self-check ok"

mkdir -p "$WT/.rsv2"

# 4. Rebase status. Behind is a warning: stale branches produce red gates that are not yours.
DEFAULT_BRANCH="$(git -C "$REPO" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')"
[ -n "$DEFAULT_BRANCH" ] || DEFAULT_BRANCH="master"
BEHIND="unknown"
if git -C "$REPO" rev-parse --verify "origin/$DEFAULT_BRANCH" >/dev/null 2>&1; then
    BEHIND="$(git -C "$REPO" rev-list --count "$HEAD_SHA..origin/$DEFAULT_BRANCH" 2>/dev/null || echo unknown)"
    if [ "$BEHIND" != "0" ] && [ "$BEHIND" != "unknown" ]; then
        say "WARNING: $BEHIND commits behind origin/$DEFAULT_BRANCH — merge before believing a red gate"
    else
        say "up to date with origin/$DEFAULT_BRANCH"
    fi
else
    say "no origin/$DEFAULT_BRANCH — skipping rebase check"
fi

# 5. Interpreter sanity. A stale venv reads modern annotations as syntax errors and fakes a wall of
# mypy failures, which has cost a session before.
PY_OK="n/a"
if [ -f "$WT/pyproject.toml" ]; then
    REQ="$(grep -m1 'requires-python' "$WT/pyproject.toml" | grep -oE '3\.[0-9]+' | head -1)"
    HAVE="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)"
    if [ -n "$REQ" ] && [ -n "$HAVE" ]; then
        if [ "$(printf '%s\n%s\n' "$REQ" "$HAVE" | sort -t. -k2 -n | head -1)" = "$REQ" ]; then
            PY_OK="ok (need $REQ, have $HAVE)"
        else
            PY_OK="STALE (need $REQ, have $HAVE)"
            say "WARNING: python $HAVE is older than the repo's $REQ — expect false mypy errors"
        fi
    fi
fi
say "python: $PY_OK"

# 6. Baseline. Auto-detect when no --gate was passed.
if [ -z "$GATES" ] && [ "$BASELINE" != "skip" ]; then
    [ -f "$WT/pyproject.toml" ] && GATES="${GATES}uv run mypy --cache-fine-grained ."$'\n'
    if [ -f "$WT/package.json" ] && grep -q '"typescript:check"' "$WT"/*/package.json "$WT/package.json" 2>/dev/null; then
        GATES="${GATES}pnpm --filter=@posthog/frontend typescript:check"$'\n'
    fi
    [ -f "$WT/go.mod" ] && GATES="${GATES}go build ./..."$'\n'
fi

RESULTS=""
if [ "$BASELINE" = "skip" ]; then
    say "baseline skipped — the pre-existing vs introduced distinction will be unavailable"
else
    OLDIFS="$IFS"; IFS=$'\n'
    for GATE in $GATES; do
        [ -n "$GATE" ] || continue
        say "baseline gate: $GATE"
        OUT="$WT/.rsv2/baseline-$(echo "$GATE" | tr -c '[:alnum:]' '-' | cut -c1-40).log"
        ( cd "$WT" && eval "$GATE" ) >"$OUT" 2>&1
        RC=$?
        say "  exit=$RC  log=$OUT"
        RESULTS="${RESULTS}{\"gate\":\"${GATE//\"/\\\"}\",\"exit\":$RC,\"log\":\"$OUT\"},"
    done
    IFS="$OLDIFS"
fi

cat > "$WT/.rsv2/preflight.json" <<EOF
{
  "repo": "$REPO",
  "branch": "$BRANCH",
  "head_sha": "$HEAD_SHA",
  "worktree": "$WT",
  "default_branch": "$DEFAULT_BRANCH",
  "behind": "$BEHIND",
  "python": "$PY_OK",
  "baseline_mode": "$BASELINE",
  "gates": [${RESULTS%,}]
}
EOF

say "summary written to $WT/.rsv2/preflight.json"
say "OK"
