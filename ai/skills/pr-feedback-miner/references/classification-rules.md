# Feedback Classification Rules

Maps human PR feedback phrasing to the priorities of the vasco-reviewer custom
agent (defined at `~/.claude/agents/vasco-reviewer.md`). Rules are applied
in priority order — the first match wins.

## Priority 1: Tests — Edge Cases

**Triggers:**
- "test for null" / "test for None" / "test when empty"
- "what if this fails" / "error case" / "exception handling test"
- "happy path only" / "only tests the success case"
- "add a test for the edge case" / "missing edge case test"

**Keywords:** null, None, empty, edge case, error case, exception, failure,
              happy path, boundary, invalid input, missing test

**Severity:** HIGH (when applied)

## Priority 2: Tests — Parameterization

**Triggers:**
- "these tests are the same" / "duplicate test"
- "parameterize" / "test.each" / "pytest.mark.parametrize"
- "same test with different input" / "copy-paste test"

**Keywords:** parameterize, parametrize, duplicate, copy-paste, same test,
              test.each, parametrize.expand

**Severity:** MEDIUM

## Priority 3: Tests — Meaningful Assertions

**Triggers:**
- "this doesn't test anything" / "what is this testing"
- "assertTrue(True)" / "trivial assertion"
- "this test would pass with empty implementation"
- "mocking the thing under test" / "the mock is the test"

**Keywords:** doesn't test, meaningless, trivial, tautology, mocking itself,
              gutted, would still pass

**Severity:** HIGH

## Priority 4: Scope Discipline

**Triggers:**
- "this change doesn't belong in this PR" / "out of scope"
- "why did this file change" / "unrelated change"
- "revert this" / "this was auto-generated"
- "separate PR" / "split this out"

**Keywords:** scope, unrelated, doesn't belong, separate PR, split out,
              auto-generated, regenerated, revert, accidental

**Severity:** MEDIUM→HIGH (HIGH if applied 3+ times across PRs)

## Priority 5: Constants Over Magic Strings

**Triggers:**
- "use the constant" / "use the enum"
- "magic string" / "magic number" / "hardcoded"
- "NodeKind." / "OrderStatus." / enum reference
- "don't use a string literal here"

**Keywords:** constant, enum, magic string, magic number, hardcoded,
              string literal, NodeKind, use the existing

**Severity:** MEDIUM

## Priority 6: Shared Helpers

**Triggers:**
- "this is duplicated" / "extract this" / "DRY"
- "same logic in X" / "copy-pasted from"
- "shared helper" / "utility function"

**Keywords:** duplicate, duplicated, extract, DRY, same logic, copy-paste,
              shared, utility, common, repeated

**Severity:** LOW→MEDIUM

## Priority 7: Refactor Hygiene

**Triggers:**
- "you renamed X but forgot" / "stale import"
- "dead code" / "unused import" / "forgot to update"
- "this reference is old" / "still references the old name"
- "shim" / "alias" / "re-export"

**Keywords:** forgot, stale, dead code, unused, old name, old reference,
              still references, shim, alias, re-export

**Severity:** MEDIUM

## Priority 8: Python Type Annotations

**Triggers:**
- "add type annotation" / "missing return type"
- "type hint" / "-> None" / ": str"
- "Any is too broad" / "be more specific with types"

**Keywords:** type annotation, type hint, return type, missing type, Any,
              TYPE_CHECKING, mypy

**Severity:** LOW

## Priority 9: Naming / Readability

**Triggers:**
- "rename this" / "confusing name"
- "double negative" / "isNotX" / "negated boolean"
- "this name doesn't match what it does"
- "hard to read" / "unclear"

**Keywords:** rename, confusing, double negative, negated, isNot, unclear,
              readability, naming

**Severity:** LOW

## Priority 10: Coupling

**Triggers:**
- "don't rely on order" / "index-based"
- "tightly coupled" / "circular dependency"
- "hardcoded selector" / "brittle test"

**Keywords:** coupling, tightly coupled, circular, order-dependent, index-based,
              hardcoded selector, brittle, fragile

**Severity:** MEDIUM

## Priority 14: Comment Discipline (added 2026-05-29 from miner run)

**Triggers:**
- "simplify this comment" / "trim this comment" / "remove this comment"
- "no need for this verbosity" / "too verbose" / "unnecessary comment"
- "focus on the WHY" / "the code already says this" / "this comment doesn't add value"
- "it's implicit" / "self-documenting" / "comment is obvious"
- "keep comments to the non-obvious why" / "why is this comment here"

**Keywords:** simplify, trim, remove comment, verbose, verbosity, verbose comment,
              implicit, obvious, self-documenting, doesn't add value, focus on the why,
              unnecessary comment, comment is longer than

**Severity:** MEDIUM (pattern repeats across PR) / LOW (single instance)

**Note:** This is the single highest-frequency pattern from the 2026-05-29 miner
scan — the user corrected agent-written comments in 5+ instances across 2 PRs.
The agent writes multi-line doc-blocks and commit-message-style inline comments
on functions whose purpose is already clear from the code.

## Priority 15: UX — Actionable Error Recovery (added 2026-05-29 from miner run)

**Triggers:**
- "are we able to link them to" / "can we add a link to" / "where do they go from here"
- "how would users fix this" / "what can they do about it"
- "this should have a button" / "add a CTA" / "needs a resolution path"
- "tells them what went wrong but not how to fix"

**Keywords:** link to billing, link to settings, button to, resolve this,
              how to fix, actionable, CTA, resolution path, next step,
              increase the limit, contact support

**Severity:** LOW

**Note:** Caught during the 2026-05-29 miner scan from MattPua's review on PR #59625.
Error states that tell users what broke but not how to resolve it are a recurring gap.

## PostHog-Specific Patterns

### `NodeKind.*` Constants
**Triggers:** "NodeKind" + any query kind string
**Maps to:** Priority 5

### `ph_scoped_capture` in Celery
**Triggers:** "posthoganalytics.capture" + context mentions "celery" or "task"
**Maps to:** Priority 5 (PostHog-specific constant)

### `team_id` Scoping
**Triggers:** "missing team_id" / "team scope" / "cross-team query"
**Maps to:** Priority 1 (edge case — data leak)

## New Pattern Detection

Any human feedback that doesn't match the triggers above is flagged as a potential
new pattern. The miner tracks these separately and proposes new vasco-reviewer
priorities when a pattern appears 2+ times.

**Example new pattern from PostHog context:**
- "Temporal activity payload too large" → vasco-reviewer PostHog section #13 (already exists)
- "Test file in wrong directory" → candidate for new priority
