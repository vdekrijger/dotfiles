---
name: review-swarm
description: Use when invoked as /review-swarm or when the user asks to review their branch, staged, or uncommitted changes locally before PRing. Local-only parallel review swarm — never posts to GitHub.
---

# Review Swarm

Local-only orchestrator. Deterministic pipeline:

```
Stage 0: diff detection
  ↓
Stage 1: simplify (edits files)  →  GATE  →  (abort or continue)
  ↓
Stage 2: parallel reviewers  (vasco + sre + xp + intent + superpowers:code-reviewer + qa-team)
  ↓
Stage 3: synthesize → write report → hand back open command
  ↓
Stage 4/5: false-positive + wins capture
```

**Hard rules:**

- **Local only.** NEVER post to GitHub — no `gh pr comment`, `gh api` writes, webhooks. All output goes to `~/Library/Caches/review-swarm/` + terminal.
- **No git writes.** NEVER `git add` / `commit` / `push` / `reset` / `checkout`. Read-only git (`status`, `diff`, `log`, `rev-parse`, `remote show`) is fine. Even if the user seems to expect it — they handle git themselves.
- **Agent independence.** Each reviewer runs as an independent subagent with zero knowledge of siblings. Never mention other reviewers, convergence/synthesis, or any "team"/"swarm" framing in a reviewer prompt. Convergence analysis has value only because the signal is uncontaminated.
- **Never skip the gate** unless `--no-gate` is explicitly passed.
- **Never modify `calibration.md` / `wins.md`** outside Stages 4/5. Never regenerate `references/prism.bundle.html` in a run. Never modify a report after it's written.

## Stage 0: diff detection

Flags:

```
--skip simplify          skip Stage 1 fixup
--skip qa-team           skip the 10-agent sub-swarm
--skip <name>            skip an individual reviewer (repeatable)
--only <name>            inverse — run only listed reviewers (repeatable)
--no-gate                don't prompt for confirmation after simplify
--base=<ref>             explicit base branch
--intent=<text-or-path>  original ask for the intent reviewer (inline text, or a path to a spec/plan file)
--uncommitted            review staged + unstaged working tree
--staged                 review staged only
--sha=<base>..<head>     explicit range
```

**Diff source resolution.** Determine current branch, repo root, and default branch (`git remote show origin … 'HEAD branch'`, fallback `main`). Honor explicit `--sha` / `--uncommitted` / `--staged` / `--base`. Otherwise:

1. Current branch ≠ default AND `git log <default>..HEAD --oneline` non-empty → branch-diff mode (base = default, head = HEAD).
2. Else if working tree or index dirty → uncommitted mode.
3. Else → print `[review-swarm] No changes to review.` and exit cleanly.

**Pass-cap on the same branch.** If 2+ prior reports exist for this branch+SHA family in `~/Library/Caches/review-swarm/${REPO_SLUG}*.html` (HEAD or ancestor, last hour), warn that pass 3+ has historically high false-positive density (diminishing returns, defense amplification) and prompt `Continue with another full pass anyway? [y/N]`, suggesting `--only vasco`, `--only code-reviewer`, or shipping as-is. Default/N → exit with pointer to the most recent report. Soft cap — `y` proceeds.

**Gather diff material** per mode:

| Mode | File list | Diff | Commits |
|---|---|---|---|
| branch-diff | `git diff <base>...HEAD --name-only` | `git diff <base>...HEAD` | `git log <base>...HEAD --oneline` |
| uncommitted | `git diff --name-only HEAD` | `git diff HEAD` | `(uncommitted)` |
| staged | `git diff --cached --name-only` | `git diff --cached` | `(uncommitted)` |

Store: mode, base ref, changed files, full diff, commit messages, HEAD SHA, repo slug (basename of repo root, non-alphanumerics → `-`).

**Per-file diffs** (drives the report's inline diff renderer): for each changed file capture the same diff command with `-U999999 -- "$f"` into `PER_FILE_DIFFS[$f]`. Empty output → record empty string (renderer shows a placeholder); `Binary files differ` → pass through verbatim. Never abort on this.

**Report path:** `REPORT_PATH="$HOME/Library/Caches/review-swarm/${REPO_SLUG}-$(date -u +%Y%m%d-%H%M%S).html"`

## Stage 1: simplify

Skip when `--skip simplify`, or `--only` without `simplify`, or the `simplify` skill isn't installed (record "simplify: skipped (not installed)", continue).

Invoke the `simplify` skill with the changed file list + diff; it edits files in place. Capture `SIMPLIFY_EDITED_FILES` via `git diff --name-only` afterward.

**Gate** (unless `--no-gate`): list the edited files, prompt `Proceed with review of simplified code? [y/N]`. `y` → Stage 2; anything else → `[review-swarm] Aborted after Stage 1. simplify edits remain in your working tree; revert with 'git checkout -- <files>' if undesired.` and exit.

If simplify errors, record `SIMPLIFY_STATUS=errored`, proceed to Stage 2 on the unmodified diff.

## Stage 2: parallel reviewer dispatch

Roster (default = all; `--only` runs just the listed ones, others skipped silently):

| Name | Invocation | Model | Skip via |
|------|------------|-------|----------|
| vasco | general-purpose subagent, reads `~/.claude/skills/vasco-reviewer/SKILL.md` | `sonnet` | `--skip vasco` |
| sre | general-purpose subagent, reads `~/.claude/skills/sre-reviewer/SKILL.md` | `opus` | `--skip sre` |
| xp | general-purpose subagent, reads `~/.claude/skills/xp-reviewer/SKILL.md` | `opus` | `--skip xp` |
| intent | general-purpose subagent, reads `~/.claude/skills/intent-reviewer/SKILL.md`; requires an intent source (below), auto-skipped with a report note when none resolves | `opus` | `--skip intent` |
| code-reviewer | subagent_type=superpowers:code-reviewer if available, else skip with warning | `sonnet` | `--skip code-reviewer` |
| qa-team | invoke the `qa-team` skill if installed; else skip silently, mark "not available on this project" | `sonnet` | `--skip qa-team` |

Model rationale: `sre`/`xp`/`intent` need opus-grade judgment for their calibration gates; `vasco`/`code-reviewer`/`qa-team` are checklist/pattern-driven, sonnet suffices. Pass `model: "<value>"` in each Agent call (only `sonnet`/`opus`/`haiku` valid); if the harness rejects the param, omit it.

**Dispatch all non-skipped reviewers in ONE message with multiple Agent tool calls** (true parallelism). Remember agent independence — no sibling/synthesis mentions.

### Prompt template per reviewer

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

   b. **For YAML / recipe / LLM-prompt content:** every named property, error code, status code, or behavior claim must be verified against actual code (grep the producer / handler / validator). Do not trust the author's wording. If you flag a claim as wrong, cite the file:line of the truth source. If you cannot verify a claim, mark the finding as `confidence: speculative`.

3. Classify each finding's **introduction**:
   - `introduced` — the PR's own code adds the issue.
   - `exposed` — pre-existing code made reachable from a new auth path / call site / hot path this PR adds.
   - `untouched` — the PR neither touches the code nor materially changes its reachability. Belongs in a separate ticket; don't inflate severity to get attention.

4. Classify each finding's **confidence**:
   - `observed-in-code` — directly visible in the diff or code you read.
   - `theoretical-worst-case` — happens under conditions you can describe concretely.
   - `speculative` — suspected but unverifiable without running code or production data.

5. Return findings in the EXACT structured format specified in your SKILL.md:

STRUCTURED_FINDINGS:
- file: <path> | line: <N or "general"> | severity: <CRITICAL|HIGH|MEDIUM|LOW|NIT> | introduction: <introduced|exposed|untouched> | confidence: <observed-in-code|theoretical-worst-case|speculative> | reviewer: $R | body: <text>
- ...

OVERALL_SUMMARY:
<one paragraph>

If no findings, emit `STRUCTURED_FINDINGS:` `(none)` plus the summary.
````

### Calibration blocks

Read `references/calibration.md` (false positives) and `references/wins.md` (confirmed catches) — both under `~/.claude/skills/review-swarm/`. For each reviewer, extract up to the last 10 entries tagged `reviewer: $R` from each file and build two blocks under `## Calibration`:

```
PAST FALSE POSITIVES — do not re-raise these patterns unless the case materially differs:
- <date> — (<repo>): "<finding body>"  (was marked FP because: <reason>)

PAST WINS — keep raising patterns like these, they landed as real catches:
- <date> — (<repo>): "<finding body>"  (WIN: <reason>)
```

Omit either block when empty. Missing file → treat as empty silently; corrupt file → log `[review-swarm] Warning: <file> parse error, treating as empty.` and continue. The `pr-feedback-miner` skill (run separately) appends human PR-review feedback into `wins.md` in the same format — ingested identically.

### intent special case

The intent reviewer gets an `## Original ask` block appended. Build it from these sources in trust order, including every one that resolves, labeled:

1. `--intent=<text-or-path>` — read the file if a path, else verbatim text.
2. Conversation context — the user's original ask(s) for this work, near-verbatim, with mid-session redirections in order (last wins).
3. PR description — `gh pr view <num> --json title,body` (read-only) + linked issue text.
4. A matching spec/plan in `docs/superpowers/specs/` or `docs/superpowers/plans/`.

Commit messages alone are NOT a sufficient intent source. If nothing resolves, skip intent and record `intent: skipped — no intent source (pass --intent= to enable)`.

### qa-team special case

qa-team is a multi-agent sub-swarm; pass the full diff, let it run its internal workflow, then flatten its findings into the common format (`reviewer: qa-team/security` etc.).

### Per-reviewer errors

A reviewer that errors → mark `$R: errored — <short error>` in the report, continue synthesis with the rest. Never abort the run.

## Stage 3: synthesize + write report

### 3a. Parse findings

Parse each reviewer's `STRUCTURED_FINDINGS:` block (`file`, `line`, `severity`, `introduction`, `confidence`, `reviewer`, `body`). Missing `introduction`/`confidence` → default `exposed` / `theoretical-worst-case` (median values; prevents grade inflation from missing tags).

Assign stable IDs 1..N in report-layout order: cross-cutting findings first (severity desc, then reviewer alpha), then file-scoped findings grouped by file (files ordered by max severity, tie-break count desc then path; within a file, severity desc, tie-break line asc, no-line last). ID #1 = most urgent.

### 3b. Convergence

Two findings converge if same `file` with lines within 5 of each other from different reviewers, OR different reviewers flag the same conceptual concern. Merge into one entry tagged with all reviewers (`[vasco + sre]`), strictest severity.

Convergent findings surface first — **only when convergence is observational**: if all merged findings are `observed-in-code`, treat as high-confidence convergent. If any is `theoretical-worst-case`/`speculative`, the merged entry inherits the *weakest* confidence and does NOT escalate severity (N reviewers theorizing the same risk likely read the same code and converged on the same hypothetical).

### 3c. Risk scoring

Compute **adjusted severity** per finding before counting:

| Original | introduced | exposed | untouched |
|---|---|---|---|
| CRITICAL | CRITICAL | HIGH | MEDIUM |
| HIGH | HIGH | MEDIUM | LOW |
| MEDIUM | MEDIUM | LOW | NIT |
| LOW | LOW | NIT | NIT |
| NIT | NIT | NIT | NIT |

Overall risk from adjusted counts: any CRITICAL → CRITICAL; 2+ HIGH or 1 HIGH + 2 MEDIUM → HIGH; 1 HIGH or 3+ MEDIUM → MEDIUM; else LOW.

The findings table shows BOTH original and adjusted severity — honest adjustment, not severity laundering.

### 3d. Verdict + grades

| Overall risk | Verdict | Grade |
|---|---|---|
| LOW | ✅ APPROVE | A |
| MEDIUM | 💬 APPROVE WITH NITS | B |
| HIGH | ⚠ REQUEST CHANGES | C |
| CRITICAL | 🚫 BLOCKED | F |

Per-reviewer grade from that reviewer's own findings (not convergence-adjusted): none/NIT → A; LOW only → A-; 1–2 MEDIUM → B+; 3+ MEDIUM → B; 1 HIGH → C+; 2+ HIGH → C; any CRITICAL → F. Skipped reviewers get `—`, not A.

### 3e. Write report

Read `~/.claude/skills/review-swarm/references/rendering.md` and follow it: render `references/report-template.html` with the documented placeholder substitutions and write to `$REPORT_PATH`.

### 3f. Hand back

Output a single open command and NOTHING else — no verdict, grade, findings, or per-reviewer takeaways in the terminal. The HTML report is the record; errored reviewers and skip notes are already inside it.

```
open <$REPORT_PATH>
```

## Stage 4: false-positive capture · Stage 5: wins capture

Two sequential optional prompts after the open command — empty input is the no-op default for both:

```
[review-swarm] Any false positives? Enter IDs (e.g. 2,5) or press Enter to skip:
[review-swarm] Any wins worth keeping (great catches you want the relevant reviewer to keep raising)? Enter IDs or skip:
```

For each provided ID: look up the finding; optionally prompt for a reason/note; append to `references/calibration.md` (FPs, Stage 4) or `references/wins.md` (wins, Stage 5) in the shared append-only format:

```
## <YYYY-MM-DD> — <repo-slug> — <report-filename>
- Finding #<ID> (<reviewer>, <severity>): <body>
  Location: <file:line>
  Marked <FP. Reason|WIN. Note>: <user-entered or "(not given)">

```

(Trailing blank line for separation.) Then confirm: `[review-swarm] Captured <M> <false positives|wins> to <path>` + `These will be surfaced to the relevant personas on next run.` Unknown IDs → warn and skip that ID. These stages are the ONLY writers of the two files.

## Graceful degradation

- Missing sibling skill (`simplify`, `qa-team`, `superpowers:code-reviewer`): warn once in the report, skip, continue (`qa-team` is PostHog-specific — skip silently elsewhere).
- No diff → `[review-swarm] No changes to review.`, no report.
- Reviewer agent errors → `[agent errored]` in report, synthesis continues.
- simplify fails → Stage 2 on unmodified diff, noted in report.
- Calibration/wins file missing or corrupt → treat as empty, warn, never fail the run.
