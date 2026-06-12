# Report rendering (Stage 3e)

The report is a single self-contained HTML file — inline CSS + vanilla JS, no external deps — rendered from `references/report-template.html`. Copy the template, substitute the placeholders below, write to `$REPORT_PATH`.

**The template already ships this UX — do not rebuild any of it:**

- Collapsible `<details>` per file (HIGH-max files open by default, lower-max closed).
- Sticky filter controls: severity checkboxes, reviewer checkboxes, "⚡ Convergent only" toggle, "Hide ✅/🟣" toggle, text search.
- Click-to-cycle status per finding: ⬜ open → ✅ addressed → 🟣 fp → ⬜. Persisted in `localStorage` under `STORAGE_KEY`; addressed rows dim, progress bar updates.
- Jump-links from the convergent quick-index to finding rows (auto-expand + flash).
- Keyboard: `/` search, `e` expand all, `c` collapse all, `Esc` reset.
- Auto light/dark theme.
- **Per-file diff renderer**: each file section's `data-diff` is rendered as a syntax-highlighted diff table (Prism, DOM builders — no innerHTML on diff text; >1 MB files skip highlighting).
- **Findings as inline annotations** in the diff at their line, status-synced with the table.
- **Free-form line comments** (hover `+` button), persisted to `<STORAGE_KEY>:comments`.
- **Feedback block button**: copies all open findings + comments as markdown (clipboard API with execCommand and visible-textarea fallbacks for `file://`).
- **Re-grade button**: rules-based recompute from currently-open findings; updates verdict banner, grade chip, per-reviewer grades in place. No LLM, no calibration writes; comments don't affect grade. Re-grade considers only ⬜ findings.

## Placeholders

| Placeholder | Contents |
|---|---|
| `{{TITLE}}` | e.g. `Review Swarm: posthog — PR #55184` |
| `{{META_ROWS}}` | `<dt>…</dt><dd>…</dd>` pairs: repo, branch/PR, base, mode, files, reviewers, date |
| `{{SUMMARY_BULLETS}}` | `<li>…</li>` per summary bullet |
| `{{VERDICT_EMOJI}}` | `✅` / `💬` / `⚠` / `🚫` |
| `{{VERDICT_TEXT}}` | `APPROVE` / `APPROVE WITH NITS` / `REQUEST CHANGES` / `BLOCKED` |
| `{{GRADE_LETTER}}` | `A` / `B+` / `C` / `F` etc. |
| `{{GRADE_CLASS}}` | lowercase grade, `-plus`/`-minus` suffix: `a`, `a-minus`, `b-plus`, `c-plus`, `f` |
| `{{VERDICT_RATIONALE}}` | 1–2 sentences |
| `{{SIMPLIFY_HEADING}}` | `Stage 1: simplify` |
| `{{SIMPLIFY_BLOCK}}` | `<p>simplify: skipped (<reason>)</p>` or `<p>simplify edited N files:</p><ul>…</ul>` |
| `{{CONVERGENT_ITEMS}}` | `<li><a class="jump" href="#finding-1">#1</a> <span style="color:var(--convergent);">[sre + qa-team/reliability]</span> <strong>HIGH</strong> — …</li>` per convergent finding |
| `{{REVIEWER_CHECKBOXES}}` | One `<label><input type="checkbox" data-filter="reviewer" value="sre" checked> sre</label>` per distinct reviewer; collapse all `qa-team/<lane>` variants into one `qa-team` checkbox |
| `{{FILE_SECTIONS}}` | One `<details class="file-section">` per file — structure below |
| `{{REVIEWER_ROWS}}` | `<tr class="reviewer-row" data-reviewer="vasco"><td>vasco</td><td>🟠 HIGH</td><td class="reviewer-grade">C</td><td>…takeaway…</td></tr>` per reviewer (class + attrs let Re-grade update grades live) |
| `{{TOTAL_FINDINGS}}` | Integer; progress-bar denominator |
| `{{GENERATED_AT}}` | UTC timestamp string |
| `{{STORAGE_KEY}}` | `review-swarm-<repo-slug>-<timestamp>` (unique per run) |
| `{{REPO_SLUG}}` | Slug as in the report filename; used in the FP-copy button's calibration header |
| `{{REPORT_FILENAME}}` | `${REPO_SLUG}-${TIMESTAMP}.html`; used in the FP-copy header |
| `{{PRISM_BUNDLE}}` | Verbatim contents of `references/prism.bundle.html` |
| `{{DIFF_BLOCK}}` | Per file section: set the section's `data-diff` attribute to the per-file diff from Stage 0, HTML-escaped |

## File section structure

One per file with findings, ordered by urgency:

```html
<details class="file-section" open data-max-severity="high">
  <summary>
    <span class="file-path">path/to/file.py</span>
    <span class="file-count"><span class="visible-count">12</span> of 12 findings · max: 🟠 High</span>
  </summary>
  <section class="file-diff" data-file="path/to/file.py" data-diff="{{DIFF_BLOCK}}"></section>
  <table class="findings">
    <thead>
      <tr><th class="col-id">ID</th><th class="col-status">Status</th><th class="col-priority">Priority</th><th class="col-line">Line</th><th>Finding</th><th class="col-reviewers">Reviewers</th><th>Fix</th></tr>
    </thead>
    <tbody>
      <tr id="finding-1" data-finding-id="1" data-severity="high" data-reviewers="sre,qa-team" class="convergent-row">
        <td class="col-id">#1</td>
        <td class="col-status"><button class="status-btn" data-status="open" title="Open (click to mark addressed)">⬜</button></td>
        <td class="col-priority priority-high">🟠 High</td>
        <td class="col-line">162, 69, general</td>
        <td>Finding body…</td>
        <td class="col-reviewers">sre + qa-team/reliability</td>
        <td>Fix suggestion…</td>
      </tr>
    </tbody>
  </table>
</details>
```

**Row data attributes (critical for JS filters):**

- `id="finding-{N}"` — jump-link target.
- `data-finding-id="{N}"` — status persistence key.
- `data-severity="critical|high|medium|low|nit"` — severity filter.
- `data-reviewers="r1,r2"` — comma-separated lowercase slugs; qa-team lanes collapse to `qa-team`.
- `class="convergent-row"` — on findings from 2+ reviewers; drives the ⚡ filter and badge.

**`open` rule:** a file section starts open if its max severity is CRITICAL or HIGH, else closed. Cross-cutting findings (no file) go in a virtual "Cross-cutting" section, same rule.

**Escaping:** HTML-escape `<`, `>`, `&`, `"` in finding bodies and fix suggestions — they come from LLM output.
