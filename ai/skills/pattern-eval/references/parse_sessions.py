#!/usr/bin/env python3
"""
Parse Claude Code session JSONL files for pattern evaluation.

Usage (from skill):
    python3 references/parse_sessions.py [--since YYYY-MM-DD] [--project-dir DIR]

Outputs JSON to stdout with:
  - summary: aggregate metrics
  - sessions: per-session breakdown with correction signals

Falls back to file mtime when sessions-index.json is stale.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Correction signal patterns (mirrors heuristics.md)
# ---------------------------------------------------------------------------

CORRECTION_PATTERNS: dict[str, list[str]] = {
    "direct_negation": [
        r"^no[,.\s!]",
        r"\bnot that\b",
        r"\bwrong\b",
        r"\bstop\b",
    ],
    "redirection": [
        r"\bI meant\b",
        r"\bI said\b",
        r"\bwhat I want\b",
        r"\binstead\b",
    ],
    "frustration": [
        r"\balready told you\b",
        r"\bI just said\b",
    ],
    "scope_correction": [
        r"\btoo much\b",
        r"\bover.?engineer\b",
        r"\bjust the\b",
    ],
    "validation_request": [
        r"\bare you sure\b",
        r"\bdouble.?check\b",
        r"\bdid you test\b",
        r"\bdid you run\b",
        r"\bverify\b",
    ],
}

# ---------------------------------------------------------------------------
# False-positive suppressors (see heuristics.md § False Positive Mitigation)
# ---------------------------------------------------------------------------

CODE_REVIEW_MARKERS = [
    "This is a comment left during a code review",
    "Comment:",
    "**",  # bold markdown in review comments
    "Path:",
    "Line:",
]

META_PREFIXES = [
    "<command-name>",
    "<command-message>",
    "<task-notification>",
]


def is_code_review_passthrough(text: str) -> bool:
    """Detect messages that are pasted code-review feedback, not user corrections."""
    return any(marker in text[:300] for marker in CODE_REVIEW_MARKERS)


def is_meta_message(text: str) -> bool:
    """Detect meta/command messages that shouldn't count as user messages."""
    stripped = text.strip()
    return any(stripped.startswith(prefix) for prefix in META_PREFIXES)


def is_trivial_session(first_prompt: str | None, user_message_count: int) -> bool:
    """Detect trivial sessions (slash commands, version checks, etc.)."""
    if user_message_count <= 1:
        return True
    if first_prompt and len(first_prompt.strip()) < 50:
        stripped = first_prompt.strip().lower()
        trivial_keywords = ["version", "test", "/clear", "<command-name>"]
        if any(kw in stripped for kw in trivial_keywords):
            return True
    return False


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text(content: str | list | None) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return " ".join(parts)
    return ""


# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------

def detect_signals(text: str, suppress_review_passthrough: bool = True) -> list[str]:
    """Detect correction signals, optionally suppressing code-review false positives."""
    if suppress_review_passthrough and is_code_review_passthrough(text):
        return []

    signals = []
    for category, patterns in CORRECTION_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                signals.append(category)
                break
    return signals


# ---------------------------------------------------------------------------
# Session discovery
# ---------------------------------------------------------------------------

def discover_project_dir() -> Path:
    """Derive the Claude project directory from CWD."""
    cwd = os.getcwd()
    # Claude stores projects under ~/.claude/projects/ with path-encoded names
    encoded = cwd.replace("/", "-")
    candidate = Path.home() / ".claude" / "projects" / encoded
    if candidate.exists():
        return candidate
    # Fall back: glob for any project dir
    projects = Path.home() / ".claude" / "projects"
    if projects.exists():
        dirs = sorted(projects.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if dirs:
            return dirs[0]
    raise FileNotFoundError(f"No Claude project directory found for {cwd}")


def find_sessions(project_dir: Path, since: datetime) -> list[tuple[Path, datetime]]:
    """Find session JSONL files modified since the cutoff date.

    Tries sessions-index.json first, falls back to file mtime if the index
    is stale (most recent entry > 7 days old).
    """
    sessions: list[tuple[Path, datetime]] = []
    index_path = project_dir / "sessions-index.json"

    use_index = False
    if index_path.exists():
        try:
            with open(index_path) as f:
                index = json.load(f)
            entries = index.get("entries", [])
            if entries:
                # Check staleness: is the most recent entry recent?
                most_recent = max(
                    (e.get("modified", "") for e in entries),
                    default=""
                )
                if most_recent:
                    most_recent_dt = datetime.fromisoformat(most_recent.replace("Z", "+00:00")).replace(tzinfo=None)
                    if (datetime.now() - most_recent_dt).days <= 7:
                        use_index = True
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    if use_index:
        for entry in entries:
            modified = entry.get("modified", "")
            if not modified:
                continue
            mod_dt = datetime.fromisoformat(modified.replace("Z", "+00:00")).replace(tzinfo=None)
            if mod_dt >= since:
                fp = Path(entry["fullPath"])
                if fp.exists():
                    sessions.append((fp, mod_dt))
    else:
        # Fallback: use file mtime
        for f in project_dir.glob("*.jsonl"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime >= since:
                sessions.append((f, mtime))

    sessions.sort(key=lambda x: x[1])
    return sessions


# ---------------------------------------------------------------------------
# Session parsing
# ---------------------------------------------------------------------------

def parse_session(filepath: Path) -> dict:
    session_id = filepath.stem
    user_messages: list[str] = []
    assistant_count = 0
    first_prompt: str | None = None

    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = entry.get("type")

            if entry_type == "user":
                if entry.get("isMeta", False):
                    continue
                msg = entry.get("message", {})
                text = extract_text(msg.get("content", ""))
                if text.strip() and not is_meta_message(text):
                    user_messages.append(text.strip())
                    if first_prompt is None:
                        first_prompt = text.strip()[:200]

            elif entry_type == "assistant":
                msg = entry.get("message", {})
                content = msg.get("content", [])
                text = extract_text(content)
                if text.strip():
                    assistant_count += 1

    # Detect correction signals
    all_corrections: list[str] = []
    correction_messages: list[dict] = []
    for msg in user_messages:
        signals = detect_signals(msg)
        if signals:
            all_corrections.extend(signals)
            correction_messages.append({"text": msg[:300], "signals": signals})

    n_user = len(user_messages)
    n_corrections = len(all_corrections)
    trivial = is_trivial_session(first_prompt, n_user)

    # Classification
    if n_user <= 2:
        classification = "one-shot"
    elif n_user <= 5:
        classification = "multi-round"
    elif n_corrections >= 2:
        classification = "struggling"
    else:
        classification = "long-but-ok"

    return {
        "session_id": session_id,
        "first_prompt": first_prompt,
        "user_message_count": n_user,
        "assistant_message_count": assistant_count,
        "classification": classification,
        "trivial": trivial,
        "correction_count": n_corrections,
        "correction_categories": list(set(all_corrections)),
        "correction_messages": correction_messages[:5],
        "user_messages_sample": [m[:300] for m in user_messages[:3]],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Parse Claude Code sessions for pattern evaluation")
    parser.add_argument("--since", help="Cutoff date (YYYY-MM-DD). Default: 7 days ago.")
    parser.add_argument("--project-dir", help="Claude project directory. Auto-detected if omitted.")
    args = parser.parse_args()

    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d")
    else:
        since = datetime.now() - timedelta(days=7)

    if args.project_dir:
        project_dir = Path(args.project_dir)
    else:
        project_dir = discover_project_dir()

    sessions = find_sessions(project_dir, since)
    results = []
    for filepath, mtime in sessions:
        try:
            result = parse_session(filepath)
            result["modified"] = mtime.isoformat()
            results.append(result)
        except Exception as e:
            results.append({"session_id": filepath.stem, "error": str(e)})

    # Summary
    valid = [r for r in results if "error" not in r]
    total = len(valid)
    non_trivial = [r for r in valid if not r.get("trivial", False)]
    one_shot_all = sum(1 for r in valid if r["classification"] == "one-shot")
    one_shot_nt = sum(1 for r in non_trivial if r["classification"] == "one-shot")
    multi_round = sum(1 for r in valid if r["classification"] == "multi-round")
    struggling = sum(1 for r in valid if r["classification"] == "struggling")
    long_ok = sum(1 for r in valid if r["classification"] == "long-but-ok")
    with_corrections = sum(1 for r in valid if r["correction_count"] > 0)
    validation_reqs = sum(1 for r in valid if "validation_request" in r.get("correction_categories", []))

    cat_counts: dict[str, int] = {}
    for r in valid:
        for cat in r.get("correction_categories", []):
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

    output = {
        "summary": {
            "total_sessions": total,
            "trivial_sessions": total - len(non_trivial),
            "non_trivial_sessions": len(non_trivial),
            "one_shot_all": one_shot_all,
            "one_shot_non_trivial": one_shot_nt,
            "one_shot_rate_all": round(one_shot_all / total * 100, 1) if total else 0,
            "one_shot_rate_non_trivial": round(one_shot_nt / len(non_trivial) * 100, 1) if non_trivial else 0,
            "multi_round": multi_round,
            "struggling": struggling,
            "long_but_ok": long_ok,
            "with_corrections": with_corrections,
            "validation_requests": validation_reqs,
            "correction_category_breakdown": cat_counts,
            "avg_user_messages": round(sum(r["user_message_count"] for r in valid) / total, 1) if total else 0,
        },
        "sessions": results,
    }

    json.dump(output, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
