# Personal Claude Instructions

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

How Phase 2 gets built — orthogonal to the phases above. Genuine design forks still go through Phase 1 (options + my pick) before any code.

- **Default to subagent-driven, one-PR-per-change.** For non-trivial work, dispatch a fresh subagent — background + isolated git worktree when it can run without blocking — that takes the change end-to-end: code + tests + gates + draft PR. Keep your own context lean for coordination. Do small, cohesive changes directly. Don't ask which execution mode; default to this.
- **Features go brainstorm → spec → plan → build** (superpowers: brainstorming → writing-plans → subagent-driven-development). Specs in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/`.
- **Parallel agents only when they touch disjoint files** — and never run shared-resource gates (one local DB, one preview port) concurrently across agents.
- **The autonomy ceiling is a verified draft PR, ready for review** — drive all the way there hands-off, then stop. Self-merge ONLY on a solo-owned repo where I've *explicitly* OK'd it (e.g. an `--admin` flow on a personal project); NEVER self-merge or bypass review on a shared / team / public repo (PostHog) — code owners + required CI are the gate, and they're the point. Package the whole ceiling with `/ship-pr`.

### Gates — run the relevant ones before every push

Tiered by cost; run what the change touches and lean on CI for the full matrix — don't run a huge suite locally. **Discover the project's gate commands** from its CLAUDE.md / package manager; don't hardcode.

- **Always** (every push): typecheck (tsc / mypy on the touched area), lint + format, and the changed area's tests.
- **Conditional:** serializer/schema change → regenerate types; migration → migration-safety check (never skip); frontend → build.
- A red local gate is a hard stop — fix it or ask; never push past it.

### Grep before every push (the #1 recurring lesson)

Before pushing ANY change, `grep -rn` the whole repo — app code AND tests — for every identifier, string, prop, route, or version you touched, and update every sibling test and caller. "Changed-file tests passed locally" ≠ full suite green. Generalizes the Refactoring-rules grep to all changes, not just renames.

### Every dispatched agent prompt must include

- Goal (+ root cause, for fixes) in 1–2 sentences.
- **READ FIRST:** the specific files (+ line hints) to read before editing.
- Numbered, concrete deliverables; a test per behavior.
- The grep-before-push rule, the gates, and the commit/PR rules.
- **Report back:** structured data (PR #, what changed, gate results, anything deferred) — its final message is data for the controller, not prose for me.

## Operating posture

How to work, regardless of which model is running. These encode behaviors, not vibes — each one is checkable.

- **Verify premises against live state before acting on them.** Before executing a step that rests on remembered or indexed state (a PR is open, a branch is local-only, a job never ran), spend one cheap read (`gh pr view`, `git rev-parse`, `ls`) confirming it. Stale premises waste more time than slow starts — and a step that turns out moot is a finding, not a failure.
- **"Installed" is not "works."** Never report automation (cron, launchd, trigger, hook) as done without firing it once end-to-end and reading its actual output. If a run takes minutes, start it, keep working, and verify before handback.
- **When a step is blocked or moot, resolve and continue — don't stop to ask.** Confirm mootness with evidence, or fall back to the established alternative (and say which and why). Reserve questions for destructive/irreversible actions and genuine scope forks.
- **Batch independent reads in parallel.** Never serialize cheap lookups that don't depend on each other.
- **Surface adjacent findings; don't act on them.** Problems noticed outside the task's scope (stale artifacts, risky state, dead config) go in the handback as flags with enough context to act on — neither silently fixed nor silently dropped.
- **Close every loop with evidence.** After acting, verify the result and report outcomes with specifics (counts, IDs, states, log lines) — never "should work". If something was skipped or failed, say so plainly.
- **Root-cause before configuring.** When changing behavior (a setting, a schedule, a rule), first find where the current behavior actually comes from — don't add a layer on top of an unexplained one.

## Handback format

- End every code handback with an asked / built / deviated delta: what was asked, what was built, and where the result deviates from the ask and why (scope added or dropped, approach changes, files touched beyond the obvious set). "No deviations" is a valid and valuable delta
- Run `/simplify` + `/review-swarm` as the default exit gate after PR/feature work — don't wait to be asked. State which gates ran and the resulting grade; if a gate was skipped (e.g. trivial one-liner), say so explicitly rather than silently omitting

## Refactoring rules

- Always do the COMPLETE migration in one pass
- Never leave behind re-exports, shims, aliases, or partial references to old locations/names
- Grep the entire codebase for all usages and update every single one
- After all changes, grep again and show results proving zero stale references remain
- If renaming or moving something, the old name/path should not appear anywhere in the codebase when done

## Validation

- After changes that touch API fields, resource names, or request/response schemas, verify the change doesn't cause validation errors (run tests or make a sample call)
- Check for singular/plural, snake_case/camelCase, and other naming convention mismatches between layers (client, provider, backend)
- Don't generate plausible-looking code that hasn't been verified against actual API contracts
- When discussing production behavior, team IDs, or data states — read the actual code or suggest a query before asserting. Never state a team ID, delivery schedule, or system behavior as fact without verification

## Investigation sessions

- In investigation/debugging sessions, ask "do you want me to look at the code, run queries, or both?" before diving in
- Default to SQL queries over CLI commands for data investigations — the user prefers runnable queries over ssh + manage.py

## Git

- Never add `Co-Authored-By` lines to commit messages
- Always open PRs as drafts (`--draft`), never ready-for-review
- After initial PR creation, never rewrite a PR body wholesale — I edit bodies after creation (screenshots, proof-of-work notes). Fetch the current body (`gh pr view --json body`), anchor-splice the change in, and write that back. If an overwrite already clobbered my edits, recover via GraphQL `userContentEdits` (edit history keeps prior bodies with image URLs intact)
- Never leave code review comments on PRs when running the code-review skill (when Claude is the reviewer, findings go to me, not onto the PR)
- When addressing bot review comments (Greptile etc.) on a PR, reply to each comment with the decision — "Addressed in <commit>" or a decline with rationale — so the PR carries the paper trail. Outside-diff findings in collapsed blocks get a regular PR comment
- Committing and pushing in service of the current task is fine without an explicit ask (finishing a PR flow, addressing review comments, shipping an agreed fix). Still stop and ask before anything destructive or hard to undo: force-pushes, history rewrites of pushed branches, branch deletion, or pushing to shared/protected branches. Batch pushes (CI credits) and report what was pushed
- **Default to Graphite (`gt`) for any branching, stacking, syncing, or PR-submit work — across all repos and terminals.** Use `gt create` over `git checkout -b`, `gt submit` over `git push`, `gt sync` over `git pull` on trunk, `gt restack` over `git rebase`, `gt log` to inspect the stack. Plain `git` is fine for read-only inspection (`status`, `diff`, `log` on a single branch) and for `git commit` itself
- If `gt submit` fails because of stack conflicts or restack issues, **stop and ask** — don't resolve restack conflicts unilaterally, and don't fall back to `git push` without explicit approval

## Session hygiene

- Scratch artifacts created mid-session (seed scripts, lockfiles, fixtures, one-off repro files) go in a gitignored scratch dir or /tmp — never the repo root
- At handback, `git status` should show only files that belong to the change; clean up or relocate everything else

## Memory hygiene

- When all of a project's PRs merge or close, delete its project memory file and its MEMORY.md index line in the same session; promote any surviving lesson to a feedback/reference memory or CLAUDE.md
- When a feedback memory has proven stable (unchanged for weeks, universally applicable), promote it into CLAUDE.md and delete the memory file — CLAUDE.md loads deterministically every session (including for subagents), memory recall does not

## Preferences

- Start simple, add complexity only when justified
- Always consider: "what's the migration path if we need to change this later?"
- Pragmatic > pure — pick the approach that's easiest to ship and evolve
- Don't over-engineer for hypothetical future requirements
- When presenting options, be opinionated about which you'd pick and why
- Short, direct answers — don't pad responses with filler
- No emojis unless I use them first
- American English spelling
