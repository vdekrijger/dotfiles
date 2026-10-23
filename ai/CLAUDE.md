# Personal Claude Instructions

Read [Vasco's shared working defaults](/Users/vasco/.codex/OPERATING_RULES.md) before applying workflow skills. Those defaults own scope, completion, verification, and follow-up behavior; the sections below retain Claude- and repository-specific context.

## Context

Primary languages: Go (dominant), Python, TypeScript, YAML (Terraform/config).
Default to the idioms and conventions of these languages without asking.

## Workflow

I work in distinct phases. Respect which phase I'm in and don't jump ahead.

### Phase 1: Explore & brainstorm

- Research the scope: what exists, what are the technical constraints, what are the tradeoffs
- Present multiple options with clear pros/cons — don't just pick one
- Consider migration paths between options (can we start simple and evolve?)
- I want to understand the problem space before committing to an approach
- Lead mechanism discussions with a small diagram before long prose — a mental-model mismatch surfaces in one picture where it survives several rounds of text
- Ask clarifying questions if the scope is ambiguous
- Define clear success criteria before diving in — don't leave sessions open-ended

### Phase 2: Iterate & build

- Once we've agreed on an approach, build it out incrementally
- Show me what it looks like — make it concrete, not theoretical
- Iterate based on my feedback; don't over-build on the first pass
- Keep changes minimal and focused on what was discussed

### Phase 3: Claude review

- Once we're both happy with the implementation, do a thorough self-review
- Review to the standard of a senior principal/distinguished engineer
- Remove dead code, unused imports, stale comments
- Check for consistency with surrounding codebase patterns
- Flag anything that feels over-engineered or under-tested
- Be honest about rough edges

### Phase 4: My review & fixes

- I'll review and make my own fixes — don't pre-empt this
- If I ask for help fixing something, fix exactly that

### Phase 5: PR support

- Help generate PR title, description, and test plan
- Follow the repo's commit/PR conventions
- Summarize what changed and why, not just what files were touched
- Include a mermaid diagram in the PR description when it clarifies a non-trivial change — architecture, data or control flow, error routing, or a key decision (GitHub renders ```mermaid fenced blocks). Skip it for trivial or mechanical changes; don't force a diagram where prose is clearer

## Execution model

Use the shared working defaults to choose process proportional to the task. For meaningful unresolved design decisions, explore options before implementation. For an agreed change, proceed through implementation and the required checks without another planning approval.

For PostHog PR completion, use `posthog-pr-finish`; for customer-flow acceptance, use `posthog-product-proof`. Keep one canonical status record for a PR stack, and avoid competing work on shared files or local services.

## Operating posture

How to work, regardless of which model is running. These encode behaviors, not vibes — each one is checkable.

- **Verify premises against live state before acting on them.** Before executing a step that rests on remembered or indexed state (a PR is open, a branch is local-only, a job never ran), spend one cheap read (`gh pr view`, `git rev-parse`, `ls`) confirming it. Stale premises waste more time than slow starts — and a step that turns out moot is a finding, not a failure.
- **"Installed" is not "works."** Never report automation (cron, launchd, trigger, hook) as done without firing it once end-to-end and reading its actual output. If a run takes minutes, start it, keep working, and verify before handback.
- **When a step is blocked or moot, resolve and continue — don't stop to ask.** Confirm mootness with evidence, or fall back to the established alternative (and say which and why). Reserve questions for destructive/irreversible actions and genuine scope forks.
- **Batch independent reads in parallel.** Never serialize cheap lookups that don't depend on each other.
- **Surface adjacent findings; don't act on them.** Problems noticed outside the task's scope (stale artifacts, risky state, dead config) go in the handback as flags with enough context to act on — neither silently fixed nor silently dropped.
- **Close every loop with evidence.** After acting, verify the result and report outcomes with specifics (counts, IDs, states, log lines) — never "should work". If something was skipped or failed, say so plainly.
- **Root-cause before configuring.** When changing behavior (a setting, a schedule, a rule), first find where the current behavior actually comes from — don't add a layer on top of an unexplained one.
- **Drive to the hard boundary, hand back one action.** When an auth or approval wall blocks the final step (Touch ID push, protected merge), finish everything up to that wall and hand back the exact command or decision needed — never stop earlier just because the last step is blocked.
- For stacks, verify each dependency and record remaining CI/acceptance gates before building on it. Repeat review for concrete changed areas or unresolved concerns; avoid review rounds that expand the agreed scope.
- **Don't block building on a pending conversation.** When a dependency is a cross-team discussion and the org norm allows it, build the code anyway, flag the dependency in the PR body, and reframe the conversation as feedback-on-code — shipped code is the better discussion artifact.

## Refactoring rules

- Always do the COMPLETE migration in one pass
- Never leave behind re-exports, shims, aliases, or partial references to old locations/names
- Grep the entire codebase for all usages and update every single one
- After all changes, grep again and show results proving zero stale references remain
- If renaming or moving something, the old name/path should not appear anywhere in the codebase when done

## Code style

Rules that keep coming back in review. They are invisible from the inside, because the author can always parse their own work, so check them explicitly rather than trusting that it reads fine.

- **One falsey type, not two.** In a type you control, never make a field or parameter both optional and nullable (`foo?: T | null`, `T[] | null | undefined`). That forces every caller to handle `undefined` and `null` for a single absent value, and each one writes a slightly different check. Pick the one the producer actually emits: a field always present in the payload is `foo: T | null`; a field whose key can be missing is `foo?: T`. Where a generated type already models it correctly, import that rather than hand-maintaining a parallel interface — codegen derives `?` and `| null` from separate backend flags and gets it right. The pattern is widespread in older handwritten types; fix what you touch rather than sweeping.
- **A call-site conditional feeding a parameter is a smell.** When callers compute a ternary just to tell a function what to do (`mode=x if cond else None`), pass the underlying domain value and branch inside the callee. The policy then lives in one place and every call site becomes unconditional.
- **Write for a reader who wasn't there.** Applies to user-facing copy, code comments, docstrings, and PR bodies alike. Before shipping a sentence, name what the reader must already know to parse it; if any of that is only learnable from the code you just wrote, rewrite it. In copy, the leaks are internal actors and verbs ("the transport", "accepted", "enqueued") and states that exist in the data model but nowhere in the UI. In comments, it's shorthand that only resolves if you are holding the call graph in your head — name the concrete caller, field, or condition instead. Compression that costs the reader the meaning is not brevity.

## Code review & simplification

- Reuse an existing framework or repo component before hand-rolling a new abstraction. Policy engines, access-control filters and permission helpers almost always already exist. If a new abstraction really is needed, justify in two sentences why the existing one does not fit, and say so before writing it
- Before claiming an API, flag or option is unsupported, or that a bug is pre-existing, verify twice by independent means: read the source, and get runtime or test evidence. State both. A confident wrong claim here has cost several rounds of rework
- Treat repeated threading as a design signal. When the same parameter, flag or modifier needs carrying through a third separate path or PR, stop before building the next one. Ask whether one decision point, where the value is produced or consumed (a printer, an executor), can decide it for every path, and present that option first. A per-query routing modifier once grew into a four-PR stack that one rule in the executor replaced
- Before a comparison or experiment mechanism becomes the production one, check that it matches the rollout unit (per query, per user, per project). A per-query opt-in suits side-by-side comparisons, not a per-project rollout

## Validation

- After changes that touch API fields, resource names, or request/response schemas, verify the change doesn't cause validation errors (run tests or make a sample call)
- Check for singular/plural, snake_case/camelCase, and other naming convention mismatches between layers (client, provider, backend)
- Don't generate plausible-looking code that hasn't been verified against actual API contracts
- When discussing production behavior, team IDs, or data states — read the actual code or suggest a query before asserting. Never state a team ID, delivery schedule, or system behavior as fact without verification

## Investigation sessions

- In investigations, infer useful read-only code and query work from the request and available access. Ask only for a missing detail that materially affects the investigation; continue independent work meanwhile
- Default to SQL queries over CLI commands for data investigations — the user prefers runnable queries over ssh + manage.py

## Debugging

- For "why isn't X happening in production?", gather runtime evidence first: events, logs, the actual network request and response, and every feature flag gating the path. Build theories from the code only after that. Three static-analysis theories once lost a session to a bug that was a read-only-mode flag blocking the POST
- After restarting or toggling any local service (celery, vite, docker), confirm it is actually running before continuing. A stopped celery worker and a stale vite bundle have each produced a long false diagnosis

## PostHog traps

Verified in real sessions; each cost a detour.

- **Alert failure paths route by error type.** In alert evaluation, `AlertExtractionError` = configuration error: the alert auto-disables and emails the owner. `AlertDataUnavailableError` = transient: the alert stays enabled and retries. Pick one deliberately for every new failure path; an unverifiable result (completeness unproven) fails closed as a config error, not a retry.
- **HogQL results consumed by code need a completeness proof.** Default limits truncate silently; a programmatic consumer sets an explicit `LimitContext` and proves the result complete (LIMIT n+1 probe / `has_more`). LIMIT is post-scan on aggregations — it caps rows returned, not bytes read, so it is not a cost lever.
- **Warehouse-synced tables lag live state.** A row that looks wrong in a synced table (an alert that "never runs", a zombie config) may be sync staleness, not product behavior. Check the sync's last refresh before diagnosing the product.
- **A cancelled CI run shows fake failures.** Unexpanded matrix jobs appear as 0-duration failures on a cancelled run. Check the run's conclusion and job durations before diagnosing any red.
- **CI red in files your branch never touched: merge master first.** A test file added on master 404s on stale branches ("file or directory not found"). Merging master is the cheap first move before deeper diagnosis.

## Git

- **Every commit must be signed** (`git commit -S`). PostHog's ruleset rejects unsigned pushes, and the posthog checkout sets `commit.gpgsign=false` locally, overriding the global `true`, so signing does not happen on its own there. Verify with `git log --show-signature -1` before pushing. Re-sign a rebased range with `git rebase --exec 'git commit --amend --no-edit -S -q --no-verify'` — without `--no-verify` a pre-commit hook that mutates files (the flox lockfile) stalls every amend; pre-push hooks still run
- Never run `git rebase --rebase-merges`, or any other history-rewriting command, on a branch that contains upstream commits. A re-sign attempt with it once rewrote 282 upstream commits
- Amending an unpublished, task-owned commit is allowed within an authorized fix. Rewriting pushed history needs explicit authorization; honor authorization already given and verify the current remote head before acting.
- Never add `Co-Authored-By` lines to commit messages
- Always open PRs as drafts (`--draft`), never ready-for-review
- After initial PR creation, never rewrite a PR body wholesale — I edit bodies after creation (screenshots, proof-of-work notes). Fetch the current body (`gh pr view --json body`), anchor-splice the change in, and write that back. If an overwrite already clobbered my edits, recover via GraphQL `userContentEdits` (edit history keeps prior bodies with image URLs intact)
- Never leave code review comments on PRs when running the code-review skill (when Claude is the reviewer, findings go to me, not onto the PR)
- When authorized to post replies while addressing bot review comments (Greptile etc.) on a PR, reply to each comment with the decision — "Addressed in <commit>" or a decline with rationale — so the PR carries the paper trail. Outside-diff findings in collapsed blocks get a regular PR comment
- Committing and pushing in service of the current task is fine without an explicit ask (finishing a PR flow, addressing review comments, shipping an agreed fix). Destructive actions, rewriting pushed history, branch deletion, and pushing to shared/protected branches require explicit authorization; honor authorization already given rather than asking again. Batch pushes (CI credits) and report what was pushed
- Never enqueue, merge, or otherwise land a PR on inferred approval, in any repo. Plan-sequence phrases ("first merge X, then Y") are not merge commands. Prepare everything, report ready, and wait for a direct instruction
- Before addressing review comments, fetch the fresh thread state (replies and recent commits) — a concurrent session may already have addressed them

## Worktrees

- Pass absolute paths to every subagent and Bash call in a worktree session. Never rely on an inherited cwd — the shell's cwd and the worktree you mean are routinely different
- Before the first edit or test run, `pwd && git rev-parse --show-toplevel` and confirm it matches the intended worktree. Abort loudly if it does not
- Never remove or reinitialize a worktree another agent may still be using

## Session hygiene

- Scratch artifacts created mid-session (seed scripts, lockfiles, fixtures, one-off repro files) go in a gitignored scratch dir or /tmp — never the repo root
- At handback, `git status` should show only files that belong to the change; clean up or relocate everything else

## Memory hygiene

Do not automatically delete or promote memories. Follow the shared working defaults and the runtime's explicit memory-update permissions. Weekly retrospectives propose one evidenced improvement for Vasco to accept.

## Preferences

- Start simple, add complexity only when justified
- Always consider: "what's the migration path if we need to change this later?"
- Pragmatic > pure — pick the approach that's easiest to ship and evolve
- Explicit over implicit for user-visible behavior: a fix must never silently inject or rewrite a user's configuration (limits, queries, settings). Surface an explicit requirement with a clear error instead
- Don't over-engineer for hypothetical future requirements
- When presenting options, be opinionated about which you'd pick and why
- Short, direct answers — don't pad responses with filler
- No emojis unless I use them first
- American English spelling
