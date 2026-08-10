# Gotchas — traps this pattern has already hit

Read before you push. Each of these cost real time or caused a real bug.

## create-vs-update field parity (the `allow_unknown_events` bug)

The PostHog API re-validates fields on **every** write, including the update PATCH. A field only
sent on create — but re-validated on update — means the resource can be created but never edited or
transitioned. `allow_unknown_events` was set only in `BuildCreateRequest`, so launching a draft
(which PATCHes the definition) re-tripped the unknown-event validation and failed.

**Rule:** map shared writable fields in one helper used by both create and update. For every
writable field, confirm in Phase 1 that the API accepts it on both. Unit-test that the update
request carries it.

Why the acceptance tests missed it: they used `$pageview` (always ingested), so validation never
fired. The **staged example run with a realistic event** caught it. This is why the example run is
a hard gate.

## Non-atomic multi-step operations

If a single apply triggers multiple API calls (e.g. create-then-launch, launch-then-ship) and one
fails midway, the resource is left mid-transition. Name the **live server state** in the error and
give a recovery hint (import/reconcile) so it isn't silently orphaned.

## Signed commits fail from the tool shell

`gpg: signing failed: Operation cancelled` — the pinentry launches on a tty the non-interactive
shell can't drive. **Fix:** prefix the commit with `export GPG_TTY=$(tty)` in the same command.
(Fallback: hand the user a `! git commit -F <msgfile>` one-liner for their own terminal.)

## zsh shell traps

The shell is zsh. `st` and `status` are taken (alias / read-only var) — a helper function named
`st` parse-errors the whole script *before* it runs, so nothing executes. Use distinct names
(`show_st`, `do_apply`). Arrays don't word-split like bash: use `VAR=(...)`; `"${VAR[@]}"`.

## Acceptance-test environment

Needs a live stack + `POSTHOG_HOST`, `POSTHOG_API_KEY` (personal), `POSTHOG_PROJECT_ID`,
`POSTHOG_ORGANIZATION_ID`. Gotchas:
- Baked-in keys go stale (401) when the dev instance is rebuilt — Claude can't mint a replacement
  (permission classifier blocks it); ask the user for a fresh one.
- `/_health` "Migrations are not up to date" is usually benign for reads/writes on an existing
  resource, but note it — it means the local schema isn't a perfect prod mirror.
- Some suites SKIP without `POSTHOG_TEST_USER_EMAIL`; that user must not be the API key's own user.
- Quota-style failures (e.g. alert limits) are environment state, not code bugs.

## Playground

Build the binary and use a `dev_overrides` `terraformrc` pointing at `bin/`; no `terraform init`
needed (it warns, that's expected). Apply from an **isolated dir** (own provider.tf with the local
host/key) so you don't disturb the checked-in `playground/` state. After a **bare-key** run,
PostHog auto-creates a flag that `destroy` leaves behind — soft-delete the orphan via the API.

## Git / PR conventions

- Draft PRs only; never merge (autonomy ceiling).
- No `Co-Authored-By` lines.
- Conventional commit messages.
- Prefer `gt` for branching/submitting; plain `git push` fast-forward is acceptable when `gt`
  fights the branch — but if `gt submit` fails on stack/restack, stop and ask.
- The dotfiles repo (where this skill lives) commits via `gt` + PRs off `main` — never commit
  skill changes onto an unrelated in-progress branch.
