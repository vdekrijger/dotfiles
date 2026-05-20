# Visual Capture Guide

Instructions for capturing visual proof artifacts during verification.

## When to Capture

Only capture visuals for criteria items with proof type `visual` or
`visual-flow`. Skip for `test`-only items and for non-UI projects.

## Screenshots (proof type: visual)

Use the browser tools (Claude in Chrome or equivalent) to capture
screenshots of specific UI states.

**Process:**
1. Navigate to the relevant page/view
2. Set up the required state (create data, trigger conditions)
3. Take a screenshot using `computer` tool with `action: screenshot`
   and `save_to_disk: true`
4. Name the file: `{REQ_ID}-{short-description}.png`
   (e.g. `req-01-widget-created.png`)
5. Store in the report's screenshots directory

**What to capture:**
- The final state that proves the requirement is satisfied
- Include enough surrounding context to show where the element is
- For error states: capture the error message/UI

## GIF Recordings (proof type: visual-flow)

Use the `gif_creator` tool to record interaction flows.

**Process:**
1. Start recording: `gif_creator` with `action: start_recording`
2. Take an initial screenshot (first frame)
3. Perform the interaction (clicks, typing, navigation)
4. Take a final screenshot (last frame)
5. Stop recording: `gif_creator` with `action: stop_recording`
6. Export: `gif_creator` with `action: export`, `download: true`
7. Name the file: `{REQ_ID}-{short-description}.gif`
   (e.g. `req-02-pagination-flow.gif`)

**What to record:**
- The full happy path or edge case interaction
- Keep it focused — 5-15 seconds max
- Ensure each click/action is visible

## Graceful Degradation

If browser tools are not available (headless environment, no Chrome
extension):
- Log a warning: `[verify-and-prove] Visual capture unavailable — skipping visual proofs`
- Mark visual items in the report as: `visual: SKIPPED (no browser tools)`
- Do NOT fail the verification — visual proof is additive, not blocking

## Storage

Visual artifacts are stored alongside the verification report:
```
docs/superpowers/verification/
  YYYY-MM-DD-<topic>-report.md
  screenshots/
    req-01-widget-created.png
    req-02-pagination-flow.gif
    ...
```

Paths are project-configurable — use whatever directory the caller specifies.
