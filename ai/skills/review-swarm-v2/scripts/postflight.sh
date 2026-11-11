#!/bin/bash
# review-swarm-v2 Stage D. Re-runs the baseline's gates in the worktree and reports each one as
# green, still-red-from-baseline, or newly red. Only newly red blocks.
set -uo pipefail

WT="" BASE_JSON="" SIGNATURES=""

die() { echo "[postflight] FAIL: $*" >&2; exit 1; }
say() { echo "[postflight] $*"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --worktree) WT="${2-}"; shift 2 ;;
        --baseline) BASE_JSON="${2-}"; shift 2 ;;
        --changed-signature) SIGNATURES="${SIGNATURES}${2-}"$'\n'; shift 2 ;;
        *) die "unknown argument: $1" ;;
    esac
done

[ -n "$WT" ] || die "--worktree is required"
[ -d "$WT" ] || die "--worktree does not exist: $WT"
WT="$(cd "$WT" && pwd -P)"   # match git's resolved path, see preflight
ACTUAL="$(git -C "$WT" rev-parse --show-toplevel 2>/dev/null)"
[ "$ACTUAL" = "$WT" ] || die "worktree self-check failed: expected $WT, got ${ACTUAL:-<none>}"
say "self-check ok: $WT"

[ -n "$BASE_JSON" ] || BASE_JSON="$WT/.rsv2/preflight.json"
[ -f "$BASE_JSON" ] || die "no baseline at $BASE_JSON — rerun preflight, or accept raw pass/fail with --baseline skip"

GATE_COUNT=$(python3 -c "import json;print(len(json.load(open('$BASE_JSON'))['gates']))" 2>/dev/null || echo 0)
if [ "$GATE_COUNT" = "0" ]; then
    say "baseline recorded no gates — every failure below is raw, not attributed"
fi

FAILED_NEW=0
i=0
while [ "$i" -lt "$GATE_COUNT" ]; do
    GATE=$(python3 -c "import json;print(json.load(open('$BASE_JSON'))['gates'][$i]['gate'])")
    WAS=$(python3 -c "import json;print(json.load(open('$BASE_JSON'))['gates'][$i]['exit'])")
    say "gate: $GATE"
    OUT="$WT/.rsv2/postflight-$(echo "$GATE" | tr -c '[:alnum:]' '-' | cut -c1-40).log"
    ( cd "$WT" && eval "$GATE" ) >"$OUT" 2>&1
    NOW=$?
    if [ "$NOW" = "0" ]; then
        if [ "$WAS" = "0" ]; then say "  GREEN (was green)"; else say "  GREEN — this run fixed a baseline failure"; fi
    elif [ "$WAS" != "0" ]; then
        say "  RED, but the baseline was red too (exit $WAS -> $NOW) — pre-existing, not yours. log=$OUT"
    else
        say "  NEWLY RED (baseline was green, now exit $NOW) — log=$OUT"
        FAILED_NEW=$((FAILED_NEW + 1))
    fi
    i=$((i + 1))
done

# Callers whose argument count no longer matches a changed signature. A heuristic that surfaces
# candidates to read; the typecheck gate above is what actually proves them.
if [ -n "$SIGNATURES" ]; then
    say "checking callers of changed signatures"
    OLDIFS="$IFS"; IFS=$'\n'
    for FN in $SIGNATURES; do
        [ -n "$FN" ] || continue
        HITS=$(grep -rn --include='*.py' --include='*.ts' --include='*.tsx' --include='*.go' -- "$FN(" "$WT" 2>/dev/null | grep -v '/.rsv2/' | head -20)
        if [ -n "$HITS" ]; then
            say "  $FN — callers to verify:"
            echo "$HITS" | sed 's/^/      /'
        else
            say "  $FN — no callers found"
        fi
    done
    IFS="$OLDIFS"
fi

# Signing. The push is rejected otherwise, and finding that out at push time costs a round trip.
SIG=$(git -C "$WT" log -1 --format='%G?' 2>/dev/null)
case "$SIG" in
    G|U|E) say "HEAD signature: $SIG (signed)" ;;
    *)     say "WARNING: HEAD is unsigned. Re-sign before pushing: git rebase --exec 'git commit --amend --no-edit -S' <base>" ;;
esac

if [ "$FAILED_NEW" -gt 0 ]; then
    say "BLOCKED: $FAILED_NEW gate(s) newly red. Do not report success."
    exit 1
fi
say "OK — no gate regressed against the baseline"
