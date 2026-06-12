# Report rendering (Stage 3e)

The report is rendered mechanically by `references/render.py` — do NOT read `report-template.html`, `prism.bundle.html`, or per-file diffs into context, and do not substitute placeholders by hand. Emit a `run.json` describing the run, then:

```
python3 ~/.claude/skills/review-swarm/references/render.py --input /tmp/review-swarm-run.json --output $REPORT_PATH
```

The script computes the per-file `-U999999` diffs itself (running git in `diff.repo_root`), HTML-escapes all LLM/user-supplied text, injects the Prism bundle, and fails loudly (non-zero exit) on missing keys or unsubstituted placeholders. Check its exit code; warnings on stderr (per-file diff failures) are non-fatal.

## run.json schema (authoritative)

```jsonc
{
  "title": "Review Swarm: posthog — PR #55184",
  "repo_slug": "posthog",                    // [A-Za-z0-9][A-Za-z0-9._-]* only
  "report_filename": "posthog-20260612-1200.html",  // same charset
  "storage_key": "review-swarm-posthog-20260612-1200", // same charset, unique per run
  "generated_at": "2026-06-12 12:00 UTC",
  "meta_rows": [["Repo", "posthog"], ["Mode", "branch-diff"]],  // [label, value] pairs
  "summary_bullets": ["…"],
  "verdict": { "emoji": "⚠", "text": "REQUEST CHANGES", "grade": "C", "grade_class": "c", "rationale": "…" },
  "simplify": { "status": "skipped|edited|errored", "reason": "…", "edited_files": ["…"] }, // reason for skipped/errored, edited_files for edited
  "diff": {
    "mode": "branch-diff|uncommitted|staged|sha-range",
    "base": "main",          // branch-diff + sha-range
    "head": "abc123",        // sha-range only
    "repo_root": "/abs/path/to/repo",
    "changed_files": ["…"]
  },
  "reviewers": [{ "name": "sre", "risk": "HIGH", "grade": "C", "takeaway": "…" }],
  "findings": [{
    "id": 1, "file": "path/to/file.py",      // or "general" for cross-cutting
    "line": "162, 69",                        // string; "general" if none
    "severity": "high", "adjusted_severity": "low",
    "introduction": "introduced|exposed|untouched",
    "confidence": "observed-in-code|theoretical-worst-case|speculative",
    "reviewers": ["sre", "qa-team/reliability"], "convergent": true,
    "body": "…", "fix": "…"
  }]
}
```

Order findings by urgency — the script groups them by file in first-appearance order (cross-cutting `"general"` findings render first), it does not re-sort. Raw text everywhere; the script escapes.

## What the script derives

File sections (open when max adjusted severity is CRITICAL/HIGH), findings rows (filter data-attributes use **adjusted** severity; when adjusted ≠ original the priority cell shows `🟠 High → Low (untouched)`), convergent quick-index, reviewer checkboxes and rows (qa-team lanes collapse to one `qa-team` slug), simplify block, totals, binary/empty diff handling. Placeholder names live in `build_substitutions()` in render.py.

The template's interactive UX — severity/reviewer filters, status cycling, re-grade, line comments, feedback/FP copy — is entirely client-side JS and untouched by this flow.
