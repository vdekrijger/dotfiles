---
name: review-swarm
description: Local-only parallel review swarm for code changes. Runs simplify (gated), then fans out vasco-reviewer + sre-reviewer + xp-reviewer + superpowers:code-reviewer + qa-team in parallel, synthesizes findings into a report at ~/Library/Caches/review-swarm/, and captures false-positive feedback for persona calibration. Use when invoked as /review-swarm or when the user asks to review their branch / uncommitted changes locally before PRing.
---

# Review Swarm

Local-only orchestrator. Runs a deterministic pipeline:

```
Stage 0: diff detection
  ↓
Stage 1: simplify (edits files)  →  GATE  →  (abort or continue)
  ↓
Stage 2: parallel reviewers  (vasco + sre + xp + superpowers:code-reviewer + qa-team)
  ↓
Stage 3: synthesize → write report → hand back open command → calibration prompt
```

**Hard rules:**

- **Local only.** NEVER use `gh pr comment`, `gh api`, or any GitHub API call. All output is local: `~/Library/Caches/review-swarm/` + terminal.
- **No git writes.** NEVER run `git add`, `git commit`, `git push`, or `git reset`. Read-only git commands (`git status`, `git diff`, `git log`, `git rev-parse`, `git remote show`) are permitted.
- **Agent independence.** Each reviewer is fired as an independent Agent subagent with zero knowledge of siblings. Never tell a reviewer that convergence analysis will run or that other reviewers exist.

## Stage 0: diff detection

Parse arguments. Supported flags:

```
--skip simplify          skip Stage 1 fixup
--skip qa-team           skip the 10-agent sub-swarm
--skip <name>            skip an individual reviewer (repeatable)
--only <name>            inverse — run only listed reviewers (repeatable)
--no-gate                don't prompt for confirmation after simplify
--base=<ref>             explicit base branch
--uncommitted            review staged + unstaged working tree
--staged                 review staged only
--sha=<base>..<head>     explicit range
```

### Diff source resolution

Run these read-only commands to classify the repo state:

```bash
git rev-parse --abbrev-ref HEAD
git rev-parse --show-toplevel
git remote show origin 2>/dev/null | grep 'HEAD branch' | awk '{print $NF}' || echo "main"
```

If the user passed `--sha=<range>`, `--uncommitted`, `--staged`, or `--base=<ref>`, honor it.

Otherwise apply auto-detect:

1. Current branch ≠ default branch AND `git log <default>..HEAD --oneline` is non-empty → branch-diff mode, base = `<default>`, head = `HEAD`.
2. Else if `git diff --quiet HEAD` fails OR `git diff --cached --quiet` fails → uncommitted mode (working tree).
3. Else → print "[review-swarm] No changes to review." and exit cleanly.

### Pass-cap on the same branch

Before dispatching reviewers, count how many prior review-swarm reports already exist for this branch in `~/Library/Caches/review-swarm/${REPO_SLUG}*.html`. If 2 or more reports already exist for the same branch+SHA family (HEAD or any ancestor in the last hour), prompt the user:

```
[review-swarm] This branch has already had N prior swarm passes. Pass 3+ has
              historically high false-positive density on PRs that have already
              addressed the major findings — diminishing returns and
              defense-amplification risk both rise sharply.

              Continue with another full pass anyway? [y/N]:
              (Or consider: --only vasco for a single-reviewer follow-up,
                            --only code-reviewer for a fast sanity check,
                            or just shipping with the current state.)
```

If the user answers `y`, proceed. Otherwise exit cleanly with `[review-swarm] Aborted — see prior report at <most-recent-path>.`

This is intentionally a soft cap — the user can always opt in. Goal: surface the diminishing-returns reality rather than dispatching another expensive pass on autopilot.

### Gather diff material

For branch-diff mode:

```bash
git diff <base>...HEAD --name-only
git diff <base>...HEAD
git log <base>...HEAD --oneline
git rev-parse HEAD
```

For uncommitted mode:

```bash
git diff --name-only HEAD
git diff HEAD
# commit messages: (uncommitted)
git rev-parse HEAD
```

For staged mode:

```bash
git diff --cached --name-only
git diff --cached
git rev-parse HEAD
```

Store: mode, base ref (if any), changed file list, full diff, commit messages (or "(uncommitted)"), HEAD SHA, repo slug (basename of repo root, non-alphanumerics → `-`), per-file diffs (`PER_FILE_DIFFS`).

### Per-file diff capture (for the report renderer)

In addition to the single-blob diff above, capture a per-file diff with full file context (`-U999999`) — this drives the inline diff renderer in the report template. Loop over every file in `$CHANGED_FILES`:

```bash
declare -A PER_FILE_DIFFS
for f in $CHANGED_FILES; do
  case "$MODE" in
    branch-diff) PER_FILE_DIFFS["$f"]="$(git diff "$BASE"...HEAD -U999999 -- "$f")" ;;
    uncommitted) PER_FILE_DIFFS["$f"]="$(git diff HEAD -U999999 -- "$f")" ;;
    staged)      PER_FILE_DIFFS["$f"]="$(git diff --cached -U999999 -- "$f")" ;;
    sha-range)   PER_FILE_DIFFS["$f"]="$(git diff "$BASE".."$HEAD" -U999999 -- "$f")" ;;
  esac
done
```

If a per-file diff comes back empty (e.g. a file appears in `--name-only` but git produces no output for it because of pathspec quirks), record an empty string — the renderer will show an "empty diff" placeholder. Do not abort.

For binary files git emits `Binary files differ`; pass that through verbatim, the renderer detects it and renders a placeholder.

### Report path

```bash
TIMESTAMP=$(date -u +%Y%m%d-%H%M%S)
REPORT_PATH="$HOME/Library/Caches/review-swarm/${REPO_SLUG}-${TIMESTAMP}.html"
```

(Subsequent stages reference `$REPORT_PATH`.)

---

## Stage 1: simplify (edits files)

**Skip conditions:**
- `--skip simplify` passed.
- `--only` passed without `simplify` in the list.
- The `simplify` skill is not installed (check: try invoking it; on "skill not found" warning, record "simplify: skipped (not installed)" and continue to Stage 2).

**Execute simplify:**

Invoke the `simplify` skill via the Skill tool. Pass the changed file list and the diff as context. Simplify will edit files in-place.

After simplify returns, capture which files it edited:

```bash
git diff --name-only
```

(In branch-diff mode, compare against the pre-simplify state — you saved HEAD earlier. The new edits are in the working tree.)

Record `SIMPLIFY_EDITED_FILES` for the final report.

**Gate:**

Unless `--no-gate` is set, print to the terminal:

```
[review-swarm] simplify edited <N> files:
  - path/one.py
  - path/two.tsx
  ...
[review-swarm] Proceed with review of simplified code? [y/N]:
```

Wait for user input.
- `y` / `Y` → continue to Stage 2.
- Anything else (including empty input) → print `[review-swarm] Aborted after Stage 1. simplify edits remain in your working tree; revert with 'git checkout -- <files>' if undesired.` and exit.

If `--no-gate` is set, skip the prompt and proceed directly to Stage 2.

**Failure handling:**

If simplify errors (merge conflict in working tree, file permission issue, etc.), record `SIMPLIFY_STATUS=errored` with the error message, skip its edits, and proceed to Stage 2 using the unmodified diff.

## Stage 2: parallel reviewer dispatch

**Reviewer roster (default = all):**

| Name | Invocation | Model | Skip via |
|------|------------|-------|----------|
| vasco | subagent_type=general-purpose, reads `~/.claude/skills/vasco-reviewer/SKILL.md` | `sonnet` | `--skip vasco` |
| sre | subagent_type=general-purpose, reads `~/.claude/skills/sre-reviewer/SKILL.md` | `opus` | `--skip sre` |
| xp | subagent_type=general-purpose, reads `~/.claude/skills/xp-reviewer/SKILL.md` | `opus` | `--skip xp` |
| code-reviewer | subagent_type=superpowers:code-reviewer (if available) else skip with warning | `sonnet` | `--skip code-reviewer` |
| qa-team | invoke the `qa-team` skill if installed; else skip silently and mark as "not available on this project" | `sonnet` | `--skip qa-team` |

**Model choice rationale.** `sre` and `xp` stay on `opus` because their calibration gates (theoretical-vs-measured, Four Rules, cost/impact weighting) require the most nuanced reasoning — cheap-model noise here defeats the whole point of the swarm. `vasco` and `code-reviewer` are checklist-driven and run well on `sonnet`. `qa-team` specialists are narrow-lane pattern matchers, `sonnet` is sufficient. Adjust if a reviewer's output quality visibly drops — it's a one-word change in the table above.

**Wiring the model param.** When dispatching each reviewer, pass `model: "<value>"` in the Agent tool call, matching the table above. Example: for the `sre` reviewer, `Agent({ subagent_type: "general-purpose", model: "opus", prompt: ... })`. If the Agent tool doesn't accept the `model` param in a particular harness, omit it — the reviewer still runs on the inherited model. Do not invent alternate values; only `sonnet`, `opus`, `haiku` are valid.

**Honor `--only`:** if set, only the listed reviewers run. Others skipped without warning.

### Dispatch rule — fire all in a single message

Launch all non-skipped reviewers via **one message with multiple Agent tool calls**. This guarantees true parallelism.

**Agent independence — hard constraint.** Each reviewer's prompt MUST NOT mention:

- The existence of other reviewers
- That a convergence / synthesis step will run
- That findings will be collapsed across agents
- Any "team" or "swarm" framing

Every reviewer believes it is the sole reviewer.

### Prompt template per reviewer

For each reviewer `$R`, build the prompt:

````
Read ~/.claude/skills/$R-reviewer/SKILL.md and follow it as your persona. (For
qa-team: follow its multi-agent workflow as documented in its SKILL.md.)

## Code changes to review

### Mode
$MODE (branch-diff / uncommitted / staged / sha-range)

### Changed files
$FILE_LIST

### Commit messages
$COMMIT_LOG

### Full diff
$FULL_DIFF

## Calibration
$PAST_FALSE_POSITIVES_BLOCK_FOR_THIS_REVIEWER

$PAST_WINS_BLOCK_FOR_THIS_REVIEWER

(If both blocks are empty, omit the entire `## Calibration` section.)

## Instructions

1. Read the full diff carefully. For each changed file, also read surrounding context (at least 50 lines above and below) using the Read tool before forming findings.

2. Apply your skill's checklist systematically. Two reviewer-discipline rules apply to every finding:

   a. **Compare against master.** Before suggesting a new defense (timeout, retry, throttle, lock, single-flight, structured logging, capture_exception wrap, etc.), grep for the analogous code path in master and verify whether master ships with that defense for similar code. If master ships without it, suggesting it for this PR is scope creep — flag the underlying gap as a separate concern (severity LOW or NIT), not a finding against this PR. Cite the file:line in master you compared against.

   b. **For YAML / recipe / LLM-prompt content:** every named property, error code, status code, or behavior claim must be verified against actual code (grep the producer / handler / validator). Do not trust the author's wording. If you flag a claim as wrong, cite the file:line of the truth source. If you cannot verify a claim, mark the finding as `confidence: speculative` (see below).

3. For each finding, classify its **introduction** (whether this PR caused it):

   - `introduced` — the PR's own code adds the issue. Newly written buggy/unsafe code.
   - `exposed` — pre-existing code is now reachable from a new auth path / call site / hot path that this PR adds. The PR doesn't change the code itself but materially changes its blast radius.
   - `untouched` — the PR doesn't touch the code AND doesn't materially change its reachability. Belongs in a separate ticket.

   Risk scoring weights these differently (see Stage 3c). Don't inflate `untouched` findings to HIGH severity to get them attention — file a separate issue instead.

4. For each finding, classify its **confidence**:

   - `observed-in-code` — the issue is directly visible in the diff or in code you read. You can point at the bytes that produce it.
   - `theoretical-worst-case` — the issue happens under specific conditions (Slack outage, N concurrent callers, deploy-time invalidation, etc.) but you can describe the conditions concretely.
   - `speculative` — you suspect an issue but couldn't verify it without running code or seeing production data.

5. Return findings in the EXACT structured format specified in your SKILL.md:

STRUCTURED_FINDINGS:
- file: <path> | line: <N or "general"> | severity: <CRITICAL|HIGH|MEDIUM|LOW|NIT> | introduction: <introduced|exposed|untouched> | confidence: <observed-in-code|theoretical-worst-case|speculative> | reviewer: $R | body: <text>
- ...

OVERALL_SUMMARY:
<one paragraph>

If no findings, emit:

STRUCTURED_FINDINGS:
(none)

OVERALL_SUMMARY:
<one paragraph>
````

### Calibration blocks (FPs and wins)

Before dispatching, read both `~/.claude/skills/review-swarm/references/calibration.md` (FPs) and `~/.claude/skills/review-swarm/references/wins.md` (confirmed catches). For each reviewer `$R`, extract up to the last 10 entries tagged `reviewer: $R` from each file and assemble two parallel prompt blocks.

**Past false positives block** (existing — unchanged shape):

```
PAST FALSE POSITIVES — do not re-raise these patterns unless the case materially differs:
- 2026-04-15 — (repo X): "<finding body>"  (was marked FP because: <reason>)
- 2026-04-18 — (repo Y): "<finding body>"  (was marked FP because: <reason>)
...
```

If no entries for this reviewer, omit the entire block.

**Past wins block** (new):

```
PAST WINS — keep raising patterns like these, they landed as real catches:
- 2026-04-15 — (repo X): "<finding body>"  (WIN: <reason>)
- 2026-04-18 — (repo Y): "<finding body>"  (WIN: <reason>)
...
```

If no entries for this reviewer, omit the entire block.

The two blocks are appended into the same `## Calibration` section of the per-reviewer prompt template, separated by a blank line. If both are empty, the entire `## Calibration` heading is omitted (same rule as today).

If `wins.md` is missing, treat as empty and continue without warning. If `wins.md` is corrupt (unparseable entries), log `[review-swarm] Warning: wins.md parse error, treating as empty.` and continue.

### qa-team special case

qa-team is itself a multi-agent sub-swarm. Dispatch it the same way but pass the full diff and let it run its internal workflow. When it returns, flatten its structured findings into the common format (reviewer: qa-team/security, qa-team/database, etc.).

### Error handling per reviewer

If a single reviewer errors during dispatch:
- Mark it as `$R: errored — <short error>` in the report.
- Continue synthesis with the reviewers that returned successfully.
- Do not abort the run.

## Stage 3: synthesize + write report

### 3a. Parse structured findings

From each reviewer's output, parse the `STRUCTURED_FINDINGS:` block. Each finding has:
- `file`, `line`, `severity`, `introduction`, `confidence`, `reviewer`, `body`

If a reviewer's output omits `introduction` or `confidence` (e.g. older calibration data, or a reviewer that didn't follow the new format), default to `introduction: exposed` and `confidence: theoretical-worst-case`. These are the median values; defaulting to them prevents grade inflation from missing-tag findings.

Assign each a stable numeric ID (1..N). The ID order follows the report layout in 3e — file-grouped, urgency-ordered — so the reader can walk through the diff file-by-file:

1. **Cross-cutting findings first** (`file: general` or empty). Within this group, sort by severity (CRITICAL → HIGH → MEDIUM → LOW → NIT), then alphabetically by reviewer.
2. **Then file-scoped findings**, grouped by file path. Files are ordered by their *max* finding severity (most urgent file first). Tie-break by finding count descending, then by path alphabetically.
3. **Within each file**, sort by severity (CRITICAL → HIGH → MEDIUM → LOW → NIT), tie-break by line number ascending (`general`/no-line sorts last within its severity bucket).

The result: ID #1 is the single most urgent cross-cutting or file-scoped finding; IDs grow as urgency drops, file by file.

### 3b. Convergence analysis

Two findings are convergent if either:
- Same `file` AND line numbers within 5 lines of each other, from different reviewers, OR
- Different reviewers flagged the same conceptual concern (e.g., both mention "missing timeout on fetch_alert_data").

Merge convergent findings into one entry tagged with all contributing reviewers (e.g., `[vasco + sre]`). Use the strictest severity of the merged findings.

Convergent findings carry higher confidence and are surfaced first in the report — **but only when convergence is observational, not speculative.** Apply this rule when merging:

- If all merged findings have `confidence: observed-in-code`, treat as high-confidence convergent (current behavior).
- If any merged finding has `confidence: theoretical-worst-case` or `speculative`, the merged entry inherits the *weakest* confidence among contributors and does NOT escalate severity beyond the strictest single contributor's level. Three reviewers theorizing the same risk is not 3× stronger than one reviewer theorizing it; they likely read the same code and converged on the same hypothetical.

### 3c. Risk scoring

Risk scoring uses **adjusted severity**, computed per-finding before counting:

| Original severity | introduction=introduced | introduction=exposed | introduction=untouched |
|---|---|---|---|
| CRITICAL | CRITICAL | HIGH | MEDIUM |
| HIGH | HIGH | MEDIUM | LOW |
| MEDIUM | MEDIUM | LOW | NIT |
| LOW | LOW | NIT | NIT |
| NIT | NIT | NIT | NIT |

Rationale: a problem the PR *introduces* is the PR's responsibility; a problem it *exposes* via a new auth path or call site is partly the PR's responsibility (worth flagging, not blocking); a problem the PR *doesn't touch* belongs in a separate ticket and shouldn't drive the grade.

Then compute overall risk from the **adjusted** severity counts:

- CRITICAL — any finding has adjusted severity CRITICAL → overall CRITICAL
- HIGH — 2+ adjusted HIGH, or 1 adjusted HIGH + 2 adjusted MEDIUM → overall HIGH
- MEDIUM — 1 adjusted HIGH, or 3+ adjusted MEDIUM → overall MEDIUM
- LOW — only adjusted LOW / NIT / none → overall LOW

The report's findings table shows BOTH the original and adjusted severity, so reviewers can see how the introduction tag changed the weight. Don't hide the original — the goal is honest adjustment, not severity laundering.

### 3d. Verdict + grade mapping

Overall grade maps 1:1 from overall risk. Verdict is the emoji banner; grade is a compact letter readers can scan at a glance.

| Overall risk | Verdict | Grade |
|---|---|---|
| LOW | ✅ APPROVE | A |
| MEDIUM | 💬 APPROVE WITH NITS | B |
| HIGH | ⚠ REQUEST CHANGES | C |
| CRITICAL | 🚫 BLOCKED | F |

**Per-reviewer grade** — computed from that reviewer's findings only (not convergence-adjusted):

| Reviewer's findings | Grade |
|---|---|
| No findings, or NIT only | A |
| LOW only (no MEDIUM/HIGH/CRITICAL) | A- |
| 1–2 MEDIUM (no HIGH/CRITICAL) | B+ |
| 3+ MEDIUM (no HIGH/CRITICAL) | B |
| 1 HIGH (no CRITICAL) | C+ |
| 2+ HIGH (no CRITICAL) | C |
| Any CRITICAL | F |

Skipped reviewers get `—` in the grade column, not `A`.

### 3e. Write report

The report is a single self-contained HTML file — inline CSS + vanilla JS, no external deps — rendered from the template at `~/.claude/skills/review-swarm/references/report-template.html`. Copy the template, substitute the placeholders below, and write the result to `$REPORT_PATH`.

**UX the template provides (do not rebuild any of this):**

- Collapsible `<details>` per file (HIGH-max files open by default, lower-max closed).
- Filter controls (sticky at top): severity checkboxes, reviewer checkboxes, "⚡ Convergent only" toggle, "Hide ✅/🟣" toggle, text search. Filter state is applied live via the embedded JS.
- Click-to-cycle status: clicking the status cell cycles ⬜ → ✅ → 🟣 → ⬜. Persisted in `localStorage` under `STORAGE_KEY`, survives reload. Addressed rows dim and the progress bar at the top updates.
- Jump-links from the convergent quick-index → the finding row: auto-expands the file section and flash-highlights the row.
- Keyboard: `/` focus search, `e` expand all, `c` collapse all, `Esc` reset filters.
- Auto light/dark theme via `prefers-color-scheme`.

**Placeholders to substitute:**

| Placeholder                   | Contents                                                                                           |
|-------------------------------|----------------------------------------------------------------------------------------------------|
| `{{TITLE}}`                   | e.g. `Review Swarm: posthog — PR #55184`                                                           |
| `{{META_ROWS}}`               | `<dt>Repo</dt><dd>…</dd>` pairs for each metadata row (repo, branch/PR, base, mode, files, reviewers, date). |
| `{{SUMMARY_BULLETS}}`         | `<li>…</li>` per summary bullet.                                                                   |
| `{{VERDICT_EMOJI}}`           | `✅` / `💬` / `⚠` / `🚫`                                                                           |
| `{{VERDICT_TEXT}}`            | `APPROVE` / `APPROVE WITH NITS` / `REQUEST CHANGES` / `BLOCKED`                                    |
| `{{GRADE_LETTER}}`            | `A` / `B+` / `C` / `F` etc.                                                                        |
| `{{GRADE_CLASS}}`             | lowercase grade with `-` for hyphens, `-plus` / `-minus` suffix. Examples: `a`, `a-minus`, `b-plus`, `c`, `c-plus`, `f`. Used for border colour. |
| `{{VERDICT_RATIONALE}}`       | 1–2 sentences.                                                                                     |
| `{{SIMPLIFY_HEADING}}`        | `Stage 1: simplify`                                                                                |
| `{{SIMPLIFY_BLOCK}}`          | `<p>simplify: skipped (<reason>)</p>` or `<p>simplify edited N files:</p><ul>...</ul>`.            |
| `{{CONVERGENT_ITEMS}}`        | `<li><a class="jump" href="#finding-1">#1</a> <span style="color:var(--convergent);">[sre + qa-team/reliability]</span> <strong>HIGH</strong> — Temporal retry re-runs...</li>` per convergent finding. |
| `{{REVIEWER_CHECKBOXES}}`     | One `<label><input type="checkbox" data-filter="reviewer" value="sre" checked> sre</label>` per distinct reviewer (collapse qa-team lanes: use `qa-team` as the value for every `qa-team/<lane>` variant so one checkbox toggles all lanes). |
| `{{FILE_SECTIONS}}`           | One `<details class="file-section" open?>` per file. See template below.                           |
| `{{REVIEWER_ROWS}}`           | `<tr class="reviewer-row" data-reviewer="vasco"><td>vasco</td><td>🟠 HIGH</td><td class="reviewer-grade">C</td><td>…takeaway…</td></tr>` per reviewer. The `reviewer-row` class + `data-reviewer` attribute + `reviewer-grade` cell let the in-report Re-grade button update each reviewer's grade live without rerunning the swarm. |
| `{{TOTAL_FINDINGS}}`          | Integer count of all findings (drives the progress bar's denominator).                             |
| `{{GENERATED_AT}}`            | UTC timestamp string.                                                                              |
| `{{STORAGE_KEY}}`             | `review-swarm-<repo-slug>-<timestamp>` (unique per run so status toggling doesn't cross-contaminate older reports). |
| `{{REPO_SLUG}}`               | Repo slug as it appears in the report filename (e.g. `posthog-pr55184` or `posthog`). Used in the FP-copy button's calibration header. |
| `{{REPORT_FILENAME}}`         | Report's own filename — `${REPO_SLUG}-${TIMESTAMP}.html`. Used in the FP-copy button's calibration header so the user knows which report the FP came from. |
| `{{PRISM_BUNDLE}}`            | Verbatim contents of `references/prism.bundle.html` (one substitution per report).                                  |
| `{{DIFF_BLOCK}}`              | Per file section: the section's `data-diff` attribute is set to the full per-file diff captured in Stage 0. HTML-escape the diff content before substituting (the JS reads `data-diff` on load and renders via DOM builders — no innerHTML on the diff text). |

**File section structure** — one of these per file with findings, ordered by urgency:

```html
<details class="file-section" open data-max-severity="high">
  <summary>
    <span class="file-path">posthog/temporal/ai/anomaly_investigation/runner.py</span>
    <span class="file-count"><span class="visible-count">12</span> of 12 findings · max: 🟠 High</span>
  </summary>
  <section class="file-diff" data-file="posthog/temporal/ai/anomaly_investigation/runner.py" data-diff="{{DIFF_BLOCK}}">
  </section>
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
        <td>Temporal retry re-runs + re-bills entire investigation…</td>
        <td class="col-reviewers">sre + qa-team/reliability</td>
        <td>Wrap both <code>ainvoke</code> calls in try/except → <code>_fallback_report</code>…</td>
      </tr>
      <!-- more rows -->
    </tbody>
  </table>
</details>
```

**Row data attributes (critical for JS filters):**

- `id="finding-{N}"` — target of jump-links from convergent index.
- `data-finding-id="{N}"` — stable key for status persistence.
- `data-severity="critical|high|medium|low|nit"` — drives severity filter.
- `data-reviewers="r1,r2,r3"` — comma-separated reviewer slugs, lowercase. For qa-team lanes use `qa-team` (drop the `/lane` — one checkbox for the whole sub-swarm).
- `class="convergent-row"` — set on findings flagged by 2+ reviewers; drives the "⚡ Convergent only" filter and the `⚡` badge.

**`open` attribute rule:** a `<details class="file-section">` starts open if the file's max severity is CRITICAL or HIGH. Otherwise starts closed. Cross-cutting findings (no specific file) go in a virtual section titled "Cross-cutting" — treat the same way.

Escape any HTML special chars (`<`, `>`, `&`, `"`) in finding bodies / fix suggestions before substitution — findings come from LLM output and may contain HTML metacharacters.

### 3f. Hand back the report

Output a single open command and nothing else — no verdict, no grade, no top-findings list, no per-reviewer takeaways. The HTML report is the record; the user opens it to read findings.

```
open <$REPORT_PATH>
```

**Do not** print findings, summaries, or highlights in the terminal. The user explicitly wants just the link. If a reviewer errored or simplify was skipped, that's already captured inside the report — don't surface it separately.

## Inline diff and comments (in-report UI)

The report template ships an interactive layer on top of the findings table:

- **Per-file diff renderer.** Each file section embeds the full unified diff captured in Stage 0 (`-U999999`) as an HTML table. Syntax-highlighted via the inlined Prism bundle by calling `Prism.highlightElement` on attached `<code>` nodes — no HTML strings are assembled. Files >1 MB skip highlighting and emit a notice.
- **Findings as inline annotations.** Every finding with a numeric line is rendered both in the per-file findings table (today) and as a coloured row inside the diff at its line. Status buttons in both surfaces are wired through one delegated handler so they stay in sync.
- **Free-form line comments.** Hovering any diff line shows a `+` button; clicking spawns a comment widget with severity dropdown, anchored to the line. Comments persist to `<STORAGE_KEY>:comments` (single JSON array). Independent of finding statuses.
- **Feedback block button.** Top-of-report. Walks all open findings + all comments, groups by severity, renders markdown, copies via `navigator.clipboard.writeText` with a hidden-textarea + `execCommand('copy')` fallback for browsers that block clipboard on `file://`. As a last resort, surfaces a visible textarea pre-selected for manual Cmd+C.
- **Re-grade button.** Top-of-report. Pure rules-based recompute from currently-open findings; updates the verdict banner, grade chip, and per-reviewer grade column in place. No LLM, no calibration writes. Free-form comments do *not* affect the grade.

Status semantics for findings: `⬜` open (default), `✅` addressed, `🟣` fp (false positive). Re-grade considers only `⬜` findings.

## Wins calibration channel

Calibration in this skill has two parallel channels:

- **`references/calibration.md`** — false positives. Captured at Stage 4. Each reviewer sees its FPs in the `PAST FALSE POSITIVES` block.
- **`references/wins.md`** — confirmed real catches. Captured at Stage 5. Each reviewer sees its wins in the `PAST WINS` block.

Both files share the same on-disk format: `## YYYY-MM-DD — <repo-slug> — <report-filename>` headers, then bulleted entries with reviewer / severity / body / location / note.

Both files are append-only and are only written by their respective stages. Manual edits are tolerated but discouraged — keep history clean.

The Stage 2 prompt builder reads up to the last 10 entries per reviewer from each file (most recent first) and emits the two prompt blocks side-by-side under one `## Calibration` heading. If a reviewer has neither FPs nor wins, the entire `## Calibration` heading is omitted (same rule as today).

## Stage 4: calibration prompt

After printing the open command, prompt the user:

```
[review-swarm] Any false positives? Enter IDs (e.g. 2,5) or press Enter to skip:
```

Wait for input.

**If empty input:** exit cleanly.

**If IDs provided:**

Parse comma-separated IDs. For each ID:

1. Look up the finding in the report (ID, reviewer, severity, file:line, body).
2. Optionally prompt: `  #<ID>: reason for marking FP? (optional, press Enter to skip):`
3. Append to `~/.claude/skills/review-swarm/references/calibration.md`:

```
## <YYYY-MM-DD> — <repo-slug> — <report-filename>
- Finding #<ID> (<reviewer>, <severity>): <body>
  Location: <file:line>
  Marked FP. Reason: <user-entered or "(not given)">

```

(Note trailing blank line for separation.)

After appending, print:

```
[review-swarm] Captured <M> false positives to ~/.claude/skills/review-swarm/references/calibration.md
[review-swarm] These will be surfaced to the relevant personas on next run.
```

### Robustness

- If calibration.md is missing when reading (Stage 2), treat as empty. Do not error.
- If calibration.md is corrupt (unparseable entries), log a warning to stdout but do not error.
- IDs that don't match any finding: print `[review-swarm] Warning: ID #<X> not found in this report, skipping.` and continue with the rest.

## Stage 5: wins capture

After Stage 4's FP prompt finishes (whether the user provided IDs or skipped), print:

```
[review-swarm] Any wins worth keeping (great catches you want the
              relevant reviewer to keep raising)? Enter IDs or skip:
```

Wait for input.

**If empty input:** print `[review-swarm] No wins captured.` and exit cleanly.

**If IDs provided:**

Parse comma-separated IDs. For each ID:

1. Look up the finding in the report (ID, reviewer, severity, file:line, body).
2. Optionally prompt: `  #<ID>: note? (optional, press Enter to skip):`
3. Append to `~/.claude/skills/review-swarm/references/wins.md`:

```
## <YYYY-MM-DD> — <repo-slug> — <report-filename>
- Finding #<ID> (<reviewer>, <severity>): <body>
  Location: <file:line>
  Marked WIN. Note: <user-entered or "(not given)">

```

(Note trailing blank line for separation, identical to calibration.md.)

After appending, print:

```
[review-swarm] Captured <M> wins to ~/.claude/skills/review-swarm/references/wins.md
[review-swarm] These will be surfaced to the relevant personas on next run.
```

### Robustness

- If `wins.md` is missing when reading (Stage 2), treat as empty. Do not error.
- If `wins.md` is corrupt (unparseable entries), log a warning to stdout but do not error.
- IDs that don't match any finding: print `[review-swarm] Warning: ID #<X> not found in this report, skipping.` and continue with the rest.
- The Stage 5 prompt is fully optional — empty input is the no-op default, identical to Stage 4's FP prompt.

## Graceful degradation

- **Missing sibling skill** (`simplify`, `qa-team`, `superpowers:code-reviewer`): warn once in the report, skip, continue. `qa-team` specifically is PostHog-specific and will be absent on other projects — skip silently, mark as "not available on this project".
- **No diff**: exit cleanly with `[review-swarm] No changes to review.` No report written.
- **A single reviewer agent errors**: mark it as `[agent errored]`, include the error in the report, continue synthesis with the remaining reviewers.
- **simplify fails to edit** (merge conflict, permission, etc.): skip Stage 1, proceed to Stage 2 on the unmodified diff, note in the report.
- **Calibration file missing or corrupt**: treat as empty, log a warning, do not fail the run.

## What NOT to do

- **Never post to GitHub.** No `gh pr comment`, no `gh api`, no webhook. Local only.
- **Never run git writes.** No `git add`, `git commit`, `git push`, `git reset`, `git checkout` (unless read-only `git rev-parse` / `git log`). Even if the user seems to expect it — they handle git themselves.
- **Never tell a reviewer about its siblings.** Agent independence is the whole game. Convergence analysis has value only because the signal is uncontaminated.
- **Never skip the gate** unless `--no-gate` is explicitly passed.
- **Never modify `calibration.md`** outside of Stage 4. No spontaneous edits.
- **Never modify `wins.md`** outside of Stage 5. No spontaneous edits.
- **Never regenerate `references/prism.bundle.html`** inside a `/review-swarm` run. It's a static asset; regeneration is a separate, manual procedure.
- **Never modify the report** after it's written. It's the record of this run.

## Invocation examples

```
# Full default run
/review-swarm

# Fast pass — skip qa-team, no gate
/review-swarm --skip qa-team --no-gate

# Only the personal reviewers
/review-swarm --only vasco --only sre

# Explicit range
/review-swarm --sha=abc123..def456

# Uncommitted only
/review-swarm --uncommitted
```
