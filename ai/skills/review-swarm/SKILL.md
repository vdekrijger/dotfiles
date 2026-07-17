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
- **Never modify `calibration.md` / `wins.md`** outside Stages 4/5 or an explicit `--distill` pass. Never regenerate `references/prism.bundle.html` in a run. Never modify a report after it's written.

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
--distill                no review; calibration maintenance pass (see Maintenance section)
--uncommitted            review staged + unstaged working tree
--staged                 review staged only
--sha=<base>..<head>     explicit range
```

**Diff source resolution.** Determine current branch, repo root, and default branch (`git remote show origin … 'HEAD branch'`, fallback `main`). Honor explicit `--sha` / `--uncommitted` / `--staged` / `--base`. Otherwise:

1. Current branch ≠ default AND `git log <default>..HEAD --oneline` non-empty → branch-diff mode (base = default, head = HEAD).
2. Else if working tree or index dirty → uncommitted mode.
3. Else → print `[review-swarm] No changes to review.` and exit cleanly.

**Pass-cap on the same branch.** If 2+ prior reports exist for this branch+SHA family in `~/Library/Caches/review-swarm/${REPO_SLUG}*.html` (HEAD or ancestor, last hour), warn that pass 3+ has historically high false-positive density (diminishing returns, defense amplification) and ask via the AskUserQuestion tool — options: "Stop — use the prior report" (recommended/first), "Run another full pass", "Single-reviewer follow-up (--only)". Stop → exit with pointer to the most recent report. Soft cap — the user can always opt in. If AskUserQuestion is unavailable, fall back to a text `[y/N]` prompt where N/default = stop.

**Gather diff material** per mode:

| Mode | File list | Diff | Commits |
|---|---|---|---|
| branch-diff | `git diff <base>...HEAD --name-only` | `git diff <base>...HEAD` | `git log <base>...HEAD --oneline` |
| uncommitted | `git diff --name-only HEAD` | `git diff HEAD` | `(uncommitted)` |
| staged | `git diff --cached --name-only` | `git diff --cached` | `(uncommitted)` |

Store: mode, base ref, changed files, full diff, commit messages, HEAD SHA, repo slug (basename of repo root, non-alphanumerics → `-`).

**Per-file diffs** (drives the report's inline diff renderer): computed by `references/render.py` at report time — do NOT capture or read `-U999999` per-file diffs yourself.

**Report path:** `REPORT_PATH="$HOME/Library/Caches/review-swarm/${REPO_SLUG}-$(date -u +%Y%m%d-%H%M%S).html"`

## Stage 1: simplify

Skip when `--skip simplify`, or `--only` without `simplify`, or the `simplify` skill isn't installed (record "simplify: skipped (not installed)", continue).

Invoke the `simplify` skill with the changed file list + diff; it edits files in place. Capture `SIMPLIFY_EDITED_FILES` via `git diff --name-only` afterward.

**Gate** (unless `--no-gate`): list the edited files, then ask via AskUserQuestion — options: "Proceed with review of simplified code" / "Abort (keep simplify edits in working tree)". Abort → print `[review-swarm] Aborted after Stage 1. simplify edits remain in your working tree; revert with 'git checkout -- <files>' if undesired.` and exit. If AskUserQuestion is unavailable, fall back to a text `[y/N]` prompt where anything but `y` aborts.

If simplify errors, record `SIMPLIFY_STATUS=errored`, proceed to Stage 2 on the unmodified diff.

## Stage 2: parallel reviewer dispatch

Roster (default = all; `--only` runs just the listed ones, others skipped silently). The four personas are custom agents defined at `~/.claude/agents/<name>.md` — the persona IS the agent's system prompt, with its model and read-only tools pinned in the agent frontmatter (vasco: sonnet; sre/xp/intent: opus — they need top-tier judgment for their calibration gates):

| Name | Invocation | Skip via |
|------|------------|----------|
| vasco | `subagent_type: vasco-reviewer` | `--skip vasco` |
| sre | `subagent_type: sre-reviewer` | `--skip sre` |
| xp | `subagent_type: xp-reviewer` | `--skip xp` |
| intent | `subagent_type: intent-reviewer`; requires an intent source (below), auto-skipped with a report note when none resolves | `--skip intent` |
| code-reviewer | `subagent_type: superpowers:code-reviewer`, `model: sonnet`; if unavailable, skip with warning | `--skip code-reviewer` |
| qa-team | general-purpose subagent (`model: sonnet`) that invokes the `qa-team` skill if installed; else skip silently, mark "not available on this project" | `--skip qa-team` |

(Valid `model` values where one is passed explicitly: `sonnet`, `opus`, `haiku`, `fable`.)

### Dispatch mechanism

**Preferred: the Workflow tool** (this skill instructing it counts as user opt-in — the user does not need to say "workflow"). The workflow owns ONLY the mechanical fan-out. Before launching, write the shared diff packet (Mode, Changed files, Commit messages, HEAD SHA, Full diff — the `## Code changes to review` block below) ONCE to a temp file:

```
PACKET_PATH="${TMPDIR:-/tmp}/review-swarm-${REPO_SLUG}-${HEAD_SHA}.md"
```

Each reviewer unit's prompt is then the persona briefing plus that packet path — the diff is never inlined into `args`, so the script and `args` stay small regardless of diff size. One `agent()` call per non-skipped reviewer, all in one `parallel()` (a single barrier is correct because Stage 3 synthesis needs every reviewer's findings together; the runtime caps concurrency itself). Findings come back schema-validated, so Stage 3a needs no text parsing and malformed output is retried by the harness. Resume after fixes is free via `resumeFromRunId`.

```js
export const meta = {
  name: 'review-swarm-dispatch',
  description: 'Fan out review-swarm reviewers in parallel',
  phases: [{ title: 'Review' }],
}
const FINDINGS_SCHEMA = {
  type: 'object', required: ['findings', 'summary'],
  properties: {
    findings: { type: 'array', items: { type: 'object',
      required: ['file', 'line', 'severity', 'introduction', 'confidence', 'body'],
      properties: {
        file: { type: 'string' }, line: { type: 'string' },
        severity: { enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NIT'] },
        introduction: { enum: ['introduced', 'exposed', 'untouched'] },
        confidence: { enum: ['observed-in-code', 'theoretical-worst-case', 'speculative'] },
        body: { type: 'string' }, fix: { type: 'string' },
      } } },
    summary: { type: 'string' },
  },
}
const results = await parallel(args.reviewers.map(r => () =>
  agent(r.prompt, { label: r.name, phase: 'Review', agentType: r.agentType, model: r.model, schema: FINDINGS_SCHEMA })
    .then(out => ({ name: r.name, out }))
))
return results
```

Pass `args.reviewers` as `[{name, agentType, model?, prompt}]`, where each `prompt` is the briefing + packet path (small — no inlined diff) (omit `model` for the four personas — their agent definitions pin it; omit `agentType` for qa-team). With the `schema` option, findings return as validated JSON — the textual `STRUCTURED_FINDINGS:` block (instruction 5b below) is only the fallback-dispatch format. A `null` slot in the results = that reviewer was skipped mid-run or errored; report it as a missing reviewer in the completion manifest (Stage 3a) — never fold it in as a completed/clean review.

**Degradation chain:**

1. **Workflow tool unavailable** → dispatch all non-skipped reviewers in ONE message with multiple Agent (plain subagent) tool calls (true parallelism), passing `subagent_type` and `model` per the roster. Reviewers return the `STRUCTURED_FINDINGS:` text block.
2. **No subagent tool at all** → run the reviewers as sequential independent passes (one after another), each with the same isolated packet-based prompt. Slower, but preserves agent independence.

Either way: agent independence — no sibling/synthesis mentions in any prompt.

### Prompt template per reviewer

The diff material lives in the packet file, so the packet-pointer + instructions are byte-identical across reviewers; persona-specific content (calibration, original-ask) comes LAST, giving parallel dispatches the longest possible cacheable prompt prefix.

The `## Code changes to review` block below is the **packet file content** — written once to `$PACKET_PATH` (see dispatch), not inlined per reviewer. Each reviewer prompt is the packet-pointer + everything from `## Instructions` onward.

````
## Code changes to review

Read the review packet at `$PACKET_PATH` in full before forming findings — it contains the mode, changed-file list, commit messages, HEAD SHA, and full diff for this review.

--- packet file ($PACKET_PATH) contents ---

### Mode
$MODE (branch-diff / uncommitted / staged / sha-range)

### Changed files
$FILE_LIST

### Commit messages
$COMMIT_LOG

### HEAD SHA
$HEAD_SHA

### Full diff
$FULL_DIFF

--- end packet file ---

## Instructions

1. Read the packet's full diff carefully. For each changed file, also read surrounding context (at least 50 lines above and below) using the Read tool before forming findings.

2. Apply your checklist systematically. (qa-team only: invoke the `qa-team` skill and follow its multi-agent workflow.) Two reviewer-discipline rules apply to every finding:

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

5. $OUTPUT_INSTRUCTION

## Calibration
$PAST_FALSE_POSITIVES_BLOCK_FOR_THIS_REVIEWER

$PAST_WINS_BLOCK_FOR_THIS_REVIEWER

(If both blocks are empty, omit the entire `## Calibration` section.)
````

`$OUTPUT_INSTRUCTION` depends on dispatch mode:

- **Workflow dispatch:** `Return your findings via the structured output schema. An empty findings array with a summary is valid output.`
- **Fallback dispatch:** `Return findings in this EXACT format:` followed by the `STRUCTURED_FINDINGS:` block (`- file: <path> | line: <N or "general"> | severity: <CRITICAL|HIGH|MEDIUM|LOW|NIT> | introduction: <…> | confidence: <…> | reviewer: $R | body: <text>`) and `OVERALL_SUMMARY:` paragraph; `(none)` + summary when no findings.

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

### 3a. Collect findings

Workflow dispatch returns schema-validated `{findings, summary}` objects — tag each finding with its reviewer name and use directly. A `null` slot (reviewer skipped or errored) is recorded as a missing reviewer in the completion manifest (`$R: errored — no result`) and gets grade `—`, never counted as a completed or clean review. Fallback dispatch: parse each reviewer's `STRUCTURED_FINDINGS:` text block (`file`, `line`, `severity`, `introduction`, `confidence`, `reviewer`, `body`); missing `introduction`/`confidence` → default `exposed` / `theoretical-worst-case` (median values; prevents grade inflation from missing tags).

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

Read `~/.claude/skills/review-swarm/references/rendering.md` and follow it: write a `run.json` describing the run, then invoke `references/render.py` to render `$REPORT_PATH` mechanically. Never read `report-template.html`, `prism.bundle.html`, or per-file diffs into context.

### 3f. Hand back

Output a single open command and NOTHING else — no verdict, grade, findings, or per-reviewer takeaways in the terminal. The HTML report is the record; errored reviewers and skip notes are already inside it.

```
open <$REPORT_PATH>
```

## Stage 4: false-positive capture · Stage 5: wins capture

Two sequential optional prompts after the open command — empty input is the no-op default for both. These stay free-text (not AskUserQuestion) because the answer is an arbitrary set of finding IDs:

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

## Maintenance: `--distill`

`/review-swarm --distill` runs INSTEAD of a review pass (no diff, no reviewers). Purpose: stop `calibration.md`/`wins.md` from growing unboundedly while their lessons get baked into the personas.

1. Read both files; count entries per reviewer.
2. For each reviewer with >15 calibration entries: identify recurring/generalizable patterns (entries often contain an explicit "Generalizable rule:" sentence) and draft a promotion — a checklist or calibration-gate edit to that persona's agent definition at `~/.claude/agents/<name>-reviewer.md`.
3. Present all proposed agent-definition edits plus the list of entries to prune (only entries whose lesson is now encoded in the persona). The user approves or rejects per proposal — never apply unapproved edits.
4. On approval: edit the agent definition, remove the distilled entries from the calibration/wins file, and summarize what moved where.

This is the only sanctioned path that modifies the calibration files outside Stages 4/5.

## Graceful degradation

- Missing sibling skill (`simplify`, `qa-team`, `superpowers:code-reviewer`): warn once in the report, skip, continue (`qa-team` is PostHog-specific — skip silently elsewhere).
- Dispatch engine: Workflow tool unavailable → plain subagent (Agent) tool in parallel; no subagent tool at all → sequential independent passes. Same packet-based prompt at every rung.
- No diff → `[review-swarm] No changes to review.`, no report.
- Reviewer agent errors or returns a `null` workflow slot → marked missing in the completion manifest (grade `—`), synthesis continues; never claimed as completed.
- simplify fails → Stage 2 on unmodified diff, noted in report.
- Calibration/wins file missing or corrupt → treat as empty, warn, never fail the run.
