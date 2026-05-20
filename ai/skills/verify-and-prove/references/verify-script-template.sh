#!/usr/bin/env bash
# ============================================================================
# Verification Script: {{TOPIC}}
# Generated: {{TIMESTAMP}}
# Criteria matrix: {{CRITERIA_PATH}}
# Re-run after any change: ./scripts/verify-{{TOPIC_SLUG}}.sh
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# --- Configuration (filled at generation time) ---
TEST_COMMAND="{{TEST_COMMAND}}"
CRITERIA_PATH="{{CRITERIA_PATH}}"
REPORT_DIR="{{REPORT_DIR}}"
TOPIC_SLUG="{{TOPIC_SLUG}}"

# --- State ---
TOTAL=0
PASS=0
FAIL=0
UNCOVERED=0
ERRORS=()

# --- Helpers ---
header() { printf "\n\033[1;34m=== %s ===\033[0m\n" "$1"; }
pass()   { PASS=$((PASS + 1)); TOTAL=$((TOTAL + 1)); printf "  \033[32m✓\033[0m %s\n" "$1"; }
fail()   { FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); ERRORS+=("FAIL: $1 — $2"); printf "  \033[31m✗\033[0m %s — %s\n" "$1" "$2"; }
skip()   { UNCOVERED=$((UNCOVERED + 1)); TOTAL=$((TOTAL + 1)); ERRORS+=("UNCOVERED: $1"); printf "  \033[33m?\033[0m %s (no test found)\n" "$1"; }

# --- Test runner ---
# Each block below corresponds to a requirement or edge case from the
# criteria matrix. The verify-and-prove skill fills these in at generation
# time based on the project's test structure.
#
# IMPORTANT: Always wrap test commands in an `if` guard. The script uses
# `set -euo pipefail` — any unguarded failing command will abort the
# entire script instead of recording the failure.
#
# Pattern:
#   header "REQ-01: <description>"
#   if <test command succeeds>; then pass "REQ-01"; else fail "REQ-01" "<reason>"; fi
#
# For edge cases without tests:
#   skip "EC-01e: <description>"

{{TEST_BLOCKS}}

# --- Summary ---
header "Verification Summary"
echo "  Total:     $TOTAL"
echo "  Pass:      $PASS"
echo "  Fail:      $FAIL"
echo "  Uncovered: $UNCOVERED"
echo ""

if [ ${#ERRORS[@]} -gt 0 ]; then
    header "Issues"
    for e in "${ERRORS[@]}"; do
        echo "  - $e"
    done
fi

# Compute status
if [ "$FAIL" -eq 0 ] && [ "$UNCOVERED" -eq 0 ]; then
    STATUS="PASS"
elif [ "$FAIL" -gt 0 ]; then
    STATUS="FAIL"
else
    STATUS="PARTIAL"
fi

# Write machine-readable summary for CI/agent consumption
mkdir -p "$REPORT_DIR"
cat > "$REPORT_DIR/verify-summary-${TOPIC_SLUG}.txt" <<SUMMARY
status=$STATUS
total=$TOTAL
pass=$PASS
fail=$FAIL
uncovered=$UNCOVERED
SUMMARY

# Exit code: non-zero if any failures or uncovered items
if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "RESULT: FAIL ($FAIL failures)"
    exit 1
elif [ "$UNCOVERED" -gt 0 ]; then
    echo ""
    echo "RESULT: PARTIAL ($UNCOVERED uncovered requirements)"
    exit 2
else
    echo ""
    echo "RESULT: PASS (all $TOTAL requirements verified)"
    exit 0
fi
