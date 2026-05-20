# PR Proof Enhancement Template

After filling in the repo's own PR template (`.github/PULL_REQUEST_TEMPLATE.md`
or equivalent), append or integrate the following proof sections.

Do NOT replace the repo's template — fill it in faithfully, then enhance
with these additions where they fit naturally.

---

## Proof Sections to Integrate

### Verification Summary

Insert into the appropriate section of the repo's template (usually
"Testing" or "How to test"):

```
**Automated Verification:**
- Criteria matrix: {TOTAL_REQUIREMENTS} requirements, {TOTAL_EDGE_CASES} edge cases
- Verification result: {PASS_COUNT}/{TOTAL_COUNT} pass, {FAIL_COUNT} fail, {UNCOVERED_COUNT} uncovered
- Review-swarm grade: {REVIEW_SWARM_GRADE}
- Rerunnable verify script: `./scripts/verify-{TOPIC_SLUG}.sh`
```

### Visual Proof

Insert screenshots and GIFs inline in the PR body. GitHub renders these
directly — reviewers see the feature without leaving the PR page.

For each visual artifact:
```
### {REQ_ID}: {DESCRIPTION}
![{REQ_ID}]({RELATIVE_PATH_TO_IMAGE})
```

Group by feature area. Put the most important flows first.

### How to Review

Insert a section guiding reviewers on what to focus on:

```
**What automated tests cover:**
- {list of what's verified — reviewers don't need to manually check these}

**What needs human review:**
- {list of items requiring judgment — UX feel, copy, layout, etc.}

**To independently verify:**
1. Check out this branch
2. Run `./scripts/verify-{TOPIC_SLUG}.sh`
3. All checks should pass with exit code 0
```

## Rules

- **Repo template first.** Always start from the repo's existing PR
  template. These proof sections enhance it, not replace it.
- **Images in the branch.** Visual artifacts must be committed to the
  branch so the relative paths resolve in the PR. Don't use absolute
  paths or external hosting.
- **Keep it scannable.** Reviewers skim PR descriptions. Use headers,
  bullet lists, and inline images — not walls of text.
- **No internal metrics.** Don't include test execution times, token
  counts, or internal operational details.
