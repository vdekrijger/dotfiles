#!/usr/bin/env python3
"""Mine human PR feedback from GitHub and classify it into reviewer calibration patterns."""

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── classification rules ───────────────────────────────────────────

PRIORITY_RULES = [
    # (priority_label, severity, triggers, keywords)
    ("1. Tests: edge cases", "HIGH", [
        r"test for (?:null|None|empty)",
        r"what if this fails",
        r"error case",
        r"exception handling test",
        r"happy path only",
        r"only tests? the success case",
        r"add a test for the edge case",
        r"missing edge case test",
        r"edge.case coverage",
    ], ["null", "None", "empty", "edge case", "error case", "exception",
        "failure", "happy path", "boundary", "invalid input", "missing test"]),
    ("2. Tests: parameterization", "MEDIUM", [
        r"these tests are the same",
        r"duplicate test",
        r"parameterize",
        r"test\.each",
        r"pytest\.mark\.parametrize",
        r"same test with different",
        r"copy.paste test",
    ], ["parameterize", "parametrize", "duplicate", "copy-paste",
        "same test", "test.each", "parametrize.expand"]),
    ("3. Tests: meaningful assertions", "HIGH", [
        r"doesn'?t test anything",
        r"what is this testing",
        r"trivial assertion",
        r"would pass with empty",
        r"would still pass",
        r"mocking (?:the thing|itself)",
        r"the mock is the test",
        r"assert(?:True|False)\(True\)",
    ], ["doesn't test", "meaningless", "trivial", "tautology",
        "mocking itself", "gutted", "would still pass"]),
    ("4. Scope discipline", "MEDIUM", [
        r"doesn'?t belong in this PR",
        r"out of scope",
        r"why did this file change",
        r"unrelated change",
        r"revert this",
        r"auto.generated",
        r"separate PR",
        r"split this out",
    ], ["scope", "unrelated", "doesn't belong", "separate PR",
        "split out", "auto-generated", "regenerated", "revert", "accidental"]),
    ("5. Constants over magic strings", "MEDIUM", [
        r"use the constant",
        r"use the enum",
        r"magic string",
        r"magic number",
        r"hardcoded",
        r"NodeKind\.",
        r"don'?t use a string literal",
    ], ["constant", "enum", "magic string", "magic number",
        "hardcoded", "string literal", "NodeKind", "use the existing"]),
    ("6. Shared helpers", "LOW", [
        r"this is duplicated",
        r"extract this",
        r"DRY",
        r"same logic in",
        r"copy.pasted from",
        r"shared helper",
        r"utility function",
    ], ["duplicate", "duplicated", "extract", "DRY", "same logic",
        "copy-paste", "shared", "utility", "common", "repeated"]),
    ("7. Refactor hygiene", "MEDIUM", [
        r"you renamed .+ but forgot",
        r"stale import",
        r"dead code",
        r"unused import",
        r"forgot to update",
        r"old (?:name|reference)",
        r"still references",
        r"shim",
        r"alias",
        r"re.export",
    ], ["forgot", "stale", "dead code", "unused", "old name",
        "old reference", "still references", "shim", "alias", "re-export"]),
    ("8. Python type annotations", "LOW", [
        r"add type annotation",
        r"missing return type",
        r"type hint",
        r"-> None",
        r": str",
        r"Any is too broad",
        r"be more specific with types",
    ], ["type annotation", "type hint", "return type", "missing type",
        "Any", "TYPE_CHECKING", "mypy"]),
    ("9. Naming / readability", "LOW", [
        r"rename this",
        r"confusing name",
        r"double negative",
        r"isNot\w+",
        r"name doesn'?t match",
        r"hard to read",
        r"unclear",
    ], ["rename", "confusing", "double negative", "negated", "isNot",
        "unclear", "readability", "naming"]),
    ("10. Coupling", "MEDIUM", [
        r"don'?t rely on order",
        r"index.based",
        r"tightly coupled",
        r"circular dependenc",
        r"hardcoded selector",
        r"brittle test",
    ], ["coupling", "tightly coupled", "circular", "order-dependent",
        "index-based", "hardcoded selector", "brittle", "fragile"]),
]

POSTHOG_SPECIFIC = [
    ("5. Constants over magic strings", "MEDIUM", [
        r"ph_scoped_capture",
        r"posthoganalytics\.capture",
    ]),
    ("1. Tests: edge cases", "HIGH", [
        r"missing team_id",
        r"team scope",
        r"cross.team query",
    ]),
]


@dataclass
class FeedbackItem:
    pr_number: int
    source: str  # "review_comment", "pr_comment", "review_body"
    author: str
    body: str
    url: str = ""
    created_at: str = ""
    was_applied: bool = False

@dataclass
class ClassifiedItem:
    item: FeedbackItem
    priority: str = ""
    severity: str = ""
    is_new_pattern: bool = False
    suggested_priority: str = ""


# ── GitHub API helpers ──────────────────────────────────────────────

def run(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, **kwargs)

def gh(*args: str) -> dict | list | None:
    """Run gh CLI and return JSON."""
    proc = run("gh", *args, timeout=120)
    if proc.returncode != 0:
        if "not found" not in proc.stderr.lower():
            print(f"[warn] gh {' '.join(args[:4])}... failed: {proc.stderr.strip()}", file=sys.stderr)
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def discover_prs(repo: str, since: str, until: str | None, limit: int, author: str | None = None) -> list[int]:
    """Find merged PRs authored by user since date."""
    search_query = f"repo:{repo} is:pr is:merged merged:>={since}"
    if author:
        search_query += f" author:{author}"
    if until:
        search_query += f" merged:<={until}"

    result = gh("search", "prs", search_query, "--limit", str(limit), "--json", "number")
    if not result:
        return []
    return sorted([pr["number"] for pr in result])


def fetch_reviews(repo: str, pr_number: int) -> list[dict]:
    """Fetch all reviews on a PR."""
    result = gh("pr", "view", str(pr_number), "--repo", repo, "--json", "reviews")
    if not result or not isinstance(result, dict):
        return []
    return result.get("reviews", [])


def fetch_pr_comments(repo: str, pr_number: int) -> list[dict]:
    """Fetch top-level PR comments (issue comments)."""
    result = gh("api", f"repos/{repo}/issues/{pr_number}/comments", "--paginate")
    if not result:
        return []
    return result if isinstance(result, list) else [result]


def fetch_review_comments(repo: str, pr_number: int) -> list[dict]:
    """Fetch inline diff review comments."""
    result = gh("api", f"repos/{repo}/pulls/{pr_number}/comments", "--paginate")
    if not result:
        return []
    return result if isinstance(result, list) else [result]


def is_bot(login: str, author_assoc: str) -> bool:
    """Check if a user is a bot."""
    bot_logins = {"dependabot", "codecov", "renovate", "github-actions",
                  "posthog-bot", "posthog-continuous-benchmarking-bot",
                  "devprod-bot", "sonarcloud", "changeset-bot"}
    if login.lower() in bot_logins:
        return True
    if author_assoc == "NONE":
        return False
    if "[bot]" in login:
        return True
    return False


# ── Classification ──────────────────────────────────────────────────

def classify_comment(body: str) -> tuple[str, str, bool, str]:
    """Classify a comment body against priority rules. Returns (priority, severity, is_new, suggested)."""
    body_lower = body.lower()

    # Check PostHog-specific rules first (they refine existing priorities)
    for priority, severity, triggers in POSTHOG_SPECIFIC:
        for trigger in triggers:
            if re.search(trigger, body_lower):
                return priority, severity, False, ""

    # Check main priority rules
    for priority, severity, triggers, keywords in PRIORITY_RULES:
        for trigger in triggers:
            if re.search(trigger, body_lower):
                return priority, severity, False, ""
        # Also check any keyword
        for kw in keywords:
            if kw.lower() in body_lower:
                return priority, severity, False, ""

    # Check for any keyword match (looser)
    for priority, severity, triggers, keywords in PRIORITY_RULES:
        for kw in keywords:
            if kw.lower() in body_lower:
                return priority, severity, False, ""

    return "", "", True, ""


# ── Main pipeline ───────────────────────────────────────────────────

def mine_pr(repo: str, pr_number: int) -> list[ClassifiedItem]:
    """Mine a single PR for feedback."""
    items: list[ClassifiedItem] = []

    # Reviews (body text in review submissions)
    reviews = fetch_reviews(repo, pr_number)
    for review in reviews:
        login = review.get("user", {}).get("login", "")
        assoc = review.get("author_association", "")
        body = review.get("body", "") or ""
        if is_bot(login, assoc):
            continue
        if not body.strip():
            continue
        # Skip approval stamps
        if body.strip().lower() in ("lgtm", "+1", "👍", "looks good", "approved"):
            continue

        fb = FeedbackItem(
            pr_number=pr_number,
            source="review_body",
            author=login,
            body=body,
            url=review.get("html_url", ""),
            created_at=review.get("submitted_at", ""),
        )
        priority, severity, is_new, suggested = classify_comment(body)
        items.append(ClassifiedItem(item=fb, priority=priority, severity=severity,
                                     is_new_pattern=is_new, suggested_priority=suggested))

    # Inline review comments
    inline_comments = fetch_review_comments(repo, pr_number)
    for comment in inline_comments:
        login = comment.get("user", {}).get("login", "")
        assoc = comment.get("author_association", "")
        body = comment.get("body", "") or ""
        if is_bot(login, assoc):
            continue
        if not body.strip():
            continue
        if body.strip().lower() in ("lgtm", "+1", "👍"):
            continue

        fb = FeedbackItem(
            pr_number=pr_number,
            source="review_comment",
            author=login,
            body=body,
            url=comment.get("html_url", ""),
            created_at=comment.get("created_at", ""),
        )
        priority, severity, is_new, suggested = classify_comment(body)
        items.append(ClassifiedItem(item=fb, priority=priority, severity=severity,
                                     is_new_pattern=is_new, suggested_priority=suggested))

    # Top-level PR comments (issue comments)
    pr_comments = fetch_pr_comments(repo, pr_number)
    for comment in pr_comments:
        login = comment.get("user", {}).get("login", "")
        assoc = comment.get("author_association", "")
        body = comment.get("body", "") or ""
        if is_bot(login, assoc):
            continue
        if not body.strip():
            continue
        if body.strip().lower() in ("lgtm", "+1", "👍"):
            continue

        fb = FeedbackItem(
            pr_number=pr_number,
            source="pr_comment",
            author=login,
            body=body,
            url=comment.get("html_url", ""),
            created_at=comment.get("created_at", ""),
        )
        priority, severity, is_new, suggested = classify_comment(body)
        items.append(ClassifiedItem(item=fb, priority=priority, severity=severity,
                                     is_new_pattern=is_new, suggested_priority=suggested))

    return items


def build_report(items: list[ClassifiedItem], repo: str, since: str,
                 until: str, prs_scanned: int) -> dict:
    """Build the structured report."""
    classified = [i for i in items if i.priority]
    unclassified = [i for i in items if i.is_new_pattern]

    pattern_counts: dict[str, dict] = {}
    for c in classified:
        if c.priority not in pattern_counts:
            pattern_counts[c.priority] = {"count": 0, "applied": 0, "examples": []}
        pattern_counts[c.priority]["count"] += 1
        if c.item.was_applied:
            pattern_counts[c.priority]["applied"] += 1
        if len(pattern_counts[c.priority]["examples"]) < 3:
            excerpt = c.item.body[:200].replace("\n", " ")
            pattern_counts[c.priority]["examples"].append(
                f"PR #{c.item.pr_number} by {c.item.author}: \"{excerpt}...\"")

    return {
        "scope": {"repo": repo, "since": since, "until": until or "now",
                  "prs_scanned": prs_scanned, "total_comments": len(items),
                  "classified": len(classified), "unclassified_new": len(unclassified)},
        "pattern_distribution": pattern_counts,
        "unclassified_patterns": [
            {"pr": u.item.pr_number, "author": u.item.author,
             "body": u.item.body[:300], "suggested": u.suggested_priority}
            for u in unclassified
        ],
    }


def format_wins_entries(items: list[ClassifiedItem], repo_slug: str) -> str:
    """Format classified items as review-swarm wins.md entries."""
    entries = []
    today = date.today().isoformat()

    for c in items:
        if not c.priority:
            continue
        entry = (
            f"## {today} — {repo_slug} — pr-feedback-miner\n"
            f"- Finding (vasco, {c.severity}): {c.priority}\n"
            f"  Location: PR #{c.item.pr_number}, {c.item.url}\n"
            f"  Marked WIN. Note: Human reviewer {c.item.author} caught this."
            f" Applied: {'yes' if c.item.was_applied else 'no'}\n"
        )
        entries.append(entry)

    return "\n".join(entries)


# ── CLI ─────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Mine PR feedback for reviewer calibration")
    parser.add_argument("--repo", help="GitHub owner/name")
    parser.add_argument("--pr", type=int, help="Single PR number")
    parser.add_argument("--since", default=(date.today() - timedelta(days=7)).isoformat())
    parser.add_argument("--until")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--local", action="store_true", help="Derive repo from git remote")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", help="Output JSON report to stdout")
    parser.add_argument("--wins-output", help="Path to output wins.md entries")
    args = parser.parse_args()

    # Resolve repo
    repo = args.repo
    author = None
    if args.local:
        proc = run("git", "remote", "get-url", "origin", cwd=os.getcwd())
        url = proc.stdout.strip()
        m = re.search(r"github\.com[:/](.+?)/(.+?)(?:\.git)?$", url)
        if m:
            repo = f"{m.group(1)}/{m.group(2)}"
        # Also try to get the current user's GH handle
        user_proc = run("gh", "api", "user", "--jq", ".login")
        if user_proc.returncode == 0:
            author = user_proc.stdout.strip()

    if not repo:
        print("Error: --repo required (or --local from a git repo)", file=sys.stderr)
        sys.exit(1)

    repo_slug = repo.replace("/", "-")

    # Discover PRs
    if args.pr:
        pr_numbers = [args.pr]
    else:
        pr_numbers = discover_prs(repo, args.since, args.until, args.limit, author)

    if not pr_numbers:
        print(f"No merged PRs found for {repo} since {args.since}")
        sys.exit(0)

    # Mine each PR
    print(f"[miner] Scanning {len(pr_numbers)} PRs in {repo}...", file=sys.stderr)
    all_items: list[ClassifiedItem] = []
    for pr_num in pr_numbers:
        items = mine_pr(repo, pr_num)
        all_items.extend(items)
        print(f"  PR #{pr_num}: {len(items)} actionable comments", file=sys.stderr)

    # Build report
    report = build_report(all_items, repo, args.since, args.until or "now", len(pr_numbers))

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"\n=== PR Feedback Miner Report ===")
        print(f"Repo: {report['scope']['repo']}")
        print(f"Range: {report['scope']['since']} → {report['scope']['until']}")
        print(f"PRs scanned: {report['scope']['prs_scanned']}")
        print(f"Total comments: {report['scope']['total_comments']}")
        print(f"Classified: {report['scope']['classified']}")
        print(f"New patterns: {report['scope']['unclassified_new']}")
        print(f"\nPattern distribution:")
        for priority, counts in sorted(report["pattern_distribution"].items()):
            print(f"  {priority}: {counts['count']} instances"
                  f" ({counts['applied']} applied)")
            for ex in counts["examples"]:
                print(f"    - {ex}")

        if report["unclassified_patterns"]:
            print(f"\nUnclassified (potential new patterns):")
            for u in report["unclassified_patterns"]:
                print(f"  PR #{u['pr']} by {u['author']}: {u['body']}")

    # Output wins entries
    if args.wins_output:
        entries = format_wins_entries(all_items, repo_slug)
        Path(args.wins_output).write_text(entries)
        print(f"\nWrote {len([i for i in all_items if i.priority])} win entries to {args.wins_output}")


if __name__ == "__main__":
    main()
