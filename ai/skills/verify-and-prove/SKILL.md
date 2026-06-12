---
name: verify-and-prove
description: Use when implementation completes, after review-swarm hardening, or when any change (simplify, refactor) needs re-verification against a criteria matrix — produces a verification report, visual proof, and a rerunnable verify script as proof of work.
---

# Verify and Prove

Walk a criteria matrix requirement by requirement: find the test, run it, capture proof. Produce a verification report and a rerunnable shell script. Use after implementation (before human checkpoint), after review-swarm hardening (before PR), after any change needing re-verification, or standalone on any project with a criteria matrix.

## Inputs

The caller provides:
1. **Criteria matrix path** — the `criteria-matrix.md` file
2. **Test command** — e.g. `npm test`, `pytest`, `go test ./...`
3. **Report directory** — default `docs/superpowers/verification/`
4. **Mode** — `full` (first run: generate script + report + visuals) or `rerun` (re-execute existing script, recapture visuals)

## Full Mode

1. **Parse the criteria matrix.** Load all REQ/EC items with proof types and priority (`must-have`/`nice-to-have`; no priority field = treat all as `must-have`).

2. **Map requirements to tests.** Search strategies in order: test name contains the REQ/EC ID (e.g. `test_req_01_create_widget`); test name describes the same behavior (grep test files for requirement keywords); test file covers the same module/function. No test found: `must-have` → UNCOVERED, `nice-to-have` → OPTIONAL.

3. **Generate the verify script** from `references/verify-script-template.sh`. Fill placeholders: `{{TOPIC}}`, `{{TOPIC_SLUG}}` (kebab-case), `{{TIMESTAMP}}` (UTC), `{{CRITERIA_PATH}}`, `{{TEST_COMMAND}}`, `{{REPORT_DIR}}`, and `{{TEST_BLOCKS}}` — one block per requirement/edge case:

   For items with tests:
   ```bash
   header "REQ-01: User can create a widget"
   if $TEST_COMMAND --filter "test_req_01" 2>&1 | tail -5; then
       pass "REQ-01"
   else
       fail "REQ-01" "test failed"
   fi
   ```

   For items without tests:
   ```bash
   header "EC-01e: Submit while offline"
   skip "EC-01e: Submit while offline"
   ```

   Write to `scripts/verify-<topic-slug>.sh` and `chmod +x`.

4. **Run the verify script**, capture output.

5. **Capture visual proof** for each `visual`/`visual-flow` item, following `references/visual-capture-guide.md`.

6. **Write the verification report** to `<report-dir>/YYYY-MM-DD-<topic>-report.md`:

   ```
   VERIFICATION_REPORT:
     spec: <spec path>
     criteria: <criteria matrix path>
     run_at: <timestamp>
     status: PASS | FAIL | PARTIAL

   RESULTS:
     - id: REQ-01 | status: PASS | tests: 3/3 | visual: screenshots/req-01-widget-created.png
     - id: EC-01a | status: PASS | tests: 1/1
     - id: EC-01b | status: FAIL | tests: 0/1 | note: <reason>

   UNCOVERED:
     - EC-01e: <description>

   OPTIONAL:
     - EC-02c: <description> (nice-to-have, no test)

   SUMMARY:
     total: N | pass: N | fail: N | uncovered: N | optional: N
     visual_artifacts: N screenshots, N gifs
   ```

   **Status:** `PASS` = all must-have pass, zero uncovered; `FAIL` = any must-have fails; `PARTIAL` = all must-have pass but some uncovered. Optional (nice-to-have) items never affect status.

## Rerun Mode

1. If `scripts/verify-<topic-slug>.sh` is missing, fall back to full mode
2. Run the existing script, capture output
3. Recapture visual proof (code may have changed)
4. Overwrite the verification report with fresh results

## Non-UI Projects

For pure backend, CLI tools, libraries: `visual`/`visual-flow` proof types simply won't appear (criteria extraction only assigns them for user-facing UI). Script and report work identically, minus visual artifact sections.

## Output

```
[verify-and-prove] Verification complete
  Status: PASS | FAIL | PARTIAL
  Results: N/N pass, N fail, N uncovered, N optional
  Report: <report path>
  Script: <script path>
  Visuals: N screenshots, N gifs
```

## Rules

- **Never fix anything.** Report only — the caller decides what to do about failures and uncovered items.
- **Never skip visual capture** for items that require it — unless browser tools are unavailable (log a warning, mark SKIPPED).
- **The verify script must be self-contained.** Runs from project root with no dependencies beyond the project's own test setup — anyone can run `./scripts/verify-<topic>.sh` and get pass/fail.
- **Rerun must be fast.** Don't regenerate the script in rerun mode — execute and recapture visuals.
- **Exit codes matter.** 0 = all pass, 1 = failures, 2 = uncovered but no failures — the skill uses these to determine report status.
