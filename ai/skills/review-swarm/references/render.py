#!/usr/bin/env python3
"""Mechanical HTML report renderer for review-swarm.

Usage:
    python3 render.py --input run.json --output /path/to/report.html

Reads the run description (run.json, schema documented in rendering.md),
computes per-file -U999999 git diffs itself, substitutes every placeholder
in report-template.html (resolved relative to this script), and writes the
final self-contained report. Exits non-zero on missing input keys or any
unsubstituted placeholder. Stdlib only.
"""

import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = SCRIPT_DIR / "report-template.html"
PRISM_PATH = SCRIPT_DIR / "prism.bundle.html"

SEVERITIES = ["critical", "high", "medium", "low", "nit"]
SEVERITY_LABEL = {
    "critical": "🔴 Critical",
    "high": "🟠 High",
    "medium": "🟡 Medium",
    "low": "🟢 Low",
    "nit": "⚪ Nit",
}
RISK_EMOJI = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢", "NIT": "⚪"}

# Substituted into a raw <script> string context as well as HTML — must stay
# out of both escaping regimes entirely.
JS_SAFE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

DIFF_MODES = {"branch-diff", "uncommitted", "staged", "sha-range"}
SIMPLIFY_STATUSES = {"skipped", "edited", "errored"}

GENERAL_FILE = "general"
GENERAL_SECTION_LABEL = "Cross-cutting"


def fail(msg: str) -> NoReturn:
    print(f"render.py: error: {msg}", file=sys.stderr)
    sys.exit(2)


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def require(obj: dict, keys: list, ctx: str) -> None:
    if not isinstance(obj, dict):
        fail(f"{ctx} must be an object, got {type(obj).__name__}")
    missing = [k for k in keys if k not in obj]
    if missing:
        fail(f"{ctx} is missing required key(s): {', '.join(missing)}")


def validate_severity(value: object, ctx: str) -> str:
    sev = str(value).lower()
    if sev not in SEVERITIES:
        fail(f"{ctx}: invalid severity {value!r} (expected one of {SEVERITIES})")
    return sev


def collapse_reviewer(name: str) -> str:
    """qa-team/<lane> collapses to qa-team for filter/data-attribute purposes."""
    slug = name.strip().lower()
    return "qa-team" if slug.startswith("qa-team/") else slug


def validate_input(run: dict) -> None:
    require(
        run,
        [
            "title", "repo_slug", "report_filename", "storage_key", "generated_at",
            "meta_rows", "summary_bullets", "verdict", "simplify", "diff",
            "reviewers", "findings",
        ],
        "run.json",
    )
    for key in ("storage_key", "repo_slug", "report_filename"):
        if not JS_SAFE_RE.match(str(run[key])):
            fail(
                f"{key} {run[key]!r} must match {JS_SAFE_RE.pattern} — it is substituted "
                "into a raw <script> string where escaping is impossible"
            )
    for i, row in enumerate(run["meta_rows"]):
        if not isinstance(row, list) or len(row) != 2:
            fail(f"meta_rows[{i}] must be a [label, value] pair")
    require(run["verdict"], ["emoji", "text", "grade", "grade_class", "rationale"], "verdict")
    simplify = run["simplify"]
    require(simplify, ["status"], "simplify")
    if simplify["status"] not in SIMPLIFY_STATUSES:
        fail(f"simplify.status {simplify['status']!r} must be one of {sorted(SIMPLIFY_STATUSES)}")
    if simplify["status"] == "edited" and "edited_files" not in simplify:
        fail("simplify.status == 'edited' requires simplify.edited_files")

    diff = run["diff"]
    require(diff, ["mode", "repo_root", "changed_files"], "diff")
    if diff["mode"] not in DIFF_MODES:
        fail(f"diff.mode {diff['mode']!r} must be one of {sorted(DIFF_MODES)}")
    if diff["mode"] in ("branch-diff", "sha-range") and not diff.get("base"):
        fail(f"diff.mode '{diff['mode']}' requires diff.base")
    if diff["mode"] == "sha-range" and not diff.get("head"):
        fail("diff.mode 'sha-range' requires diff.head")

    for i, reviewer in enumerate(run["reviewers"]):
        require(reviewer, ["name", "risk", "grade", "takeaway"], f"reviewers[{i}]")
    for i, finding in enumerate(run["findings"]):
        require(
            finding,
            ["id", "file", "line", "severity", "adjusted_severity", "introduction",
             "confidence", "reviewers", "convergent", "body", "fix"],
            f"findings[{i}]",
        )
        validate_severity(finding["severity"], f"findings[{i}].severity")
        validate_severity(finding["adjusted_severity"], f"findings[{i}].adjusted_severity")
        if not finding["reviewers"]:
            fail(f"findings[{i}].reviewers must be non-empty")


# ───── per-file diffs ─────────────────────────────────────────────────────────

def diff_command(diff: dict, file_path: str) -> list:
    mode = diff["mode"]
    if mode == "branch-diff":
        return ["git", "diff", "-U999999", f"{diff['base']}...HEAD", "--", file_path]
    if mode == "uncommitted":
        return ["git", "diff", "-U999999", "HEAD", "--", file_path]
    if mode == "staged":
        return ["git", "diff", "--cached", "-U999999", "--", file_path]
    # sha-range
    return ["git", "diff", "-U999999", f"{diff['base']}..{diff['head']}", "--", file_path]


def compute_file_diff(diff: dict, file_path: str) -> str:
    """Run the mode-appropriate git diff for one file. Never raises:
    empty/missing output -> "", binary -> the verbatim 'Binary files …' marker
    line (the template's renderer requires the diff to START with it)."""
    try:
        proc = subprocess.run(
            diff_command(diff, file_path),
            cwd=diff["repo_root"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"render.py: warning: git diff failed for {file_path}: {exc}", file=sys.stderr)
        return ""
    if proc.returncode != 0:
        print(
            f"render.py: warning: git diff exited {proc.returncode} for {file_path}: "
            f"{proc.stderr.strip()}",
            file=sys.stderr,
        )
        return ""
    out = proc.stdout
    for line in out.splitlines():
        if line.startswith("Binary files"):
            return line
    return out


# ───── fragment builders ──────────────────────────────────────────────────────

def reviewers_display(names: list) -> str:
    return " + ".join(str(n).strip() for n in names)


def reviewers_data_attr(names: list) -> str:
    collapsed = [collapse_reviewer(str(n)) for n in names]
    return ",".join(dict.fromkeys(collapsed))


def priority_cell(finding: dict) -> str:
    original = validate_severity(finding["severity"], "finding.severity")
    adjusted = validate_severity(finding["adjusted_severity"], "finding.adjusted_severity")
    title = f"confidence: {finding['confidence']} · introduction: {finding['introduction']}"
    if original == adjusted:
        text = SEVERITY_LABEL[original]
    else:
        # The template's findings table has no adjusted-severity column, so the
        # adjustment renders as a suffix: "🟠 High → Low (untouched)".
        text = f"{SEVERITY_LABEL[original]} → {adjusted.capitalize()} ({finding['introduction']})"
    return f'<td class="col-priority priority-{adjusted}" title="{esc(title)}">{esc(text)}</td>'


def finding_row(finding: dict) -> str:
    fid = finding["id"]
    adjusted = str(finding["adjusted_severity"]).lower()
    convergent_class = ' class="convergent-row"' if finding["convergent"] else ""
    return (
        f'<tr id="finding-{fid}" data-finding-id="{fid}" data-severity="{adjusted}" '
        f'data-reviewers="{esc(reviewers_data_attr(finding["reviewers"]))}"{convergent_class}>\n'
        f'        <td class="col-id">#{fid}</td>\n'
        f'        <td class="col-status"><button class="status-btn" data-status="open" '
        f'title="Open (click to mark addressed)">⬜</button></td>\n'
        f"        {priority_cell(finding)}\n"
        f'        <td class="col-line">{esc(finding["line"])}</td>\n'
        f"        <td>{esc(finding['body'])}</td>\n"
        f'        <td class="col-reviewers">{esc(reviewers_display(finding["reviewers"]))}</td>\n'
        f"        <td>{esc(finding['fix'])}</td>\n"
        f"      </tr>"
    )


def group_findings_by_file(findings: list) -> list:
    """[(file, [finding, ...]), ...] in first-appearance order, 'general' first."""
    groups: dict = {}
    for finding in findings:
        groups.setdefault(str(finding["file"]), []).append(finding)
    ordered = list(groups.items())
    ordered.sort(key=lambda kv: 0 if kv[0] == GENERAL_FILE else 1)  # stable: general first
    return ordered


def max_adjusted_severity(findings: list) -> str:
    return min(
        (str(f["adjusted_severity"]).lower() for f in findings),
        key=SEVERITIES.index,
    )


def file_section(file_path: str, findings: list, diff: dict) -> str:
    max_sev = max_adjusted_severity(findings)
    open_attr = " open" if max_sev in ("critical", "high") else ""
    is_general = file_path == GENERAL_FILE
    display_path = GENERAL_SECTION_LABEL if is_general else file_path
    count = len(findings)
    noun = "finding" if count == 1 else "findings"

    if is_general:
        diff_html = ""  # virtual section: no diff to render
    else:
        diff_text = compute_file_diff(diff, file_path)
        diff_html = (
            f'  <section class="file-diff" data-file="{esc(file_path)}" '
            f'data-diff="{esc(diff_text)}"></section>\n'
        )

    rows = "\n      ".join(finding_row(f) for f in findings)
    return (
        f'<details class="file-section"{open_attr} data-max-severity="{max_sev}">\n'
        f"  <summary>\n"
        f'    <span class="file-path">{esc(display_path)}</span>\n'
        f'    <span class="file-count"><span class="visible-count">{count}</span> '
        f"of {count} {noun} · max: {SEVERITY_LABEL[max_sev]}</span>\n"
        f"  </summary>\n"
        f"{diff_html}"
        f'  <table class="findings">\n'
        f"    <thead>\n"
        f'      <tr><th class="col-id">ID</th><th class="col-status">Status</th>'
        f'<th class="col-priority">Priority</th><th class="col-line">Line</th>'
        f'<th>Finding</th><th class="col-reviewers">Reviewers</th><th>Fix</th></tr>\n'
        f"    </thead>\n"
        f"    <tbody>\n"
        f"      {rows}\n"
        f"    </tbody>\n"
        f"  </table>\n"
        f"</details>"
    )


def build_file_sections(run: dict) -> str:
    grouped = group_findings_by_file(run["findings"])
    return "\n    ".join(file_section(path, items, run["diff"]) for path, items in grouped)


def truncate(text: str, limit: int = 140) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1].rstrip() + "…"


def build_convergent_items(findings: list) -> str:
    items = []
    for finding in findings:
        if not finding["convergent"]:
            continue
        original = str(finding["severity"]).upper()
        adjusted = str(finding["adjusted_severity"]).upper()
        sev = original if original == adjusted else f"{original}→{adjusted}"
        location = f"{finding['file']}:{finding['line']}"
        items.append(
            f'<li><a class="jump" href="#finding-{finding["id"]}">#{finding["id"]}</a> '
            f'<span style="color:var(--convergent);">[{esc(reviewers_display(finding["reviewers"]))}]</span> '
            f"<strong>{esc(sev)}</strong> — {esc(location)} — {esc(truncate(str(finding['body'])))}</li>"
        )
    if not items:
        return '<li style="color:var(--fg-muted);">None — no finding was flagged by 2+ reviewers.</li>'
    return "\n      ".join(items)


def build_reviewer_checkboxes(run: dict) -> str:
    slugs: dict = {}
    for reviewer in run["reviewers"]:
        slugs.setdefault(collapse_reviewer(str(reviewer["name"])), None)
    for finding in run["findings"]:
        for name in finding["reviewers"]:
            slugs.setdefault(collapse_reviewer(str(name)), None)
    return "\n      ".join(
        f'<label><input type="checkbox" data-filter="reviewer" value="{esc(slug)}" checked> {esc(slug)}</label>'
        for slug in slugs
    )


def build_reviewer_rows(reviewers: list) -> str:
    rows = []
    for reviewer in reviewers:
        slug = collapse_reviewer(str(reviewer["name"]))
        risk = str(reviewer["risk"]).strip()
        emoji = RISK_EMOJI.get(risk.upper())
        risk_text = f"{emoji} {risk.upper()}" if emoji else risk
        rows.append(
            f'<tr class="reviewer-row" data-reviewer="{esc(slug)}">'
            f"<td>{esc(reviewer['name'])}</td>"
            f"<td>{esc(risk_text)}</td>"
            f'<td class="reviewer-grade">{esc(reviewer["grade"])}</td>'
            f"<td>{esc(reviewer['takeaway'])}</td></tr>"
        )
    return "\n        ".join(rows)


def build_simplify_block(simplify: dict) -> str:
    status = simplify["status"]
    if status == "edited":
        files = simplify["edited_files"]
        items = "".join(f"<li><code>{esc(f)}</code></li>" for f in files)
        noun = "file" if len(files) == 1 else "files"
        return f"<p>simplify edited {len(files)} {noun}:</p><ul>{items}</ul>"
    reason = simplify.get("reason", "no reason given")
    return f"<p>simplify: {esc(status)} ({esc(reason)})</p>"


def build_meta_rows(meta_rows: list) -> str:
    return "\n      ".join(
        f"<dt>{esc(label)}</dt><dd>{esc(value)}</dd>" for label, value in meta_rows
    )


def build_summary_bullets(bullets: list) -> str:
    return "\n      ".join(f"<li>{esc(b)}</li>" for b in bullets)


# ───── substitution ───────────────────────────────────────────────────────────

PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_]+)\}\}")


def build_substitutions(run: dict) -> dict:
    verdict = run["verdict"]
    return {
        "TITLE": esc(run["title"]),
        "META_ROWS": build_meta_rows(run["meta_rows"]),
        "SUMMARY_BULLETS": build_summary_bullets(run["summary_bullets"]),
        "VERDICT_EMOJI": esc(verdict["emoji"]),
        "VERDICT_TEXT": esc(verdict["text"]),
        "GRADE_LETTER": esc(verdict["grade"]),
        "GRADE_CLASS": esc(verdict["grade_class"]),
        "VERDICT_RATIONALE": esc(verdict["rationale"]),
        "SIMPLIFY_HEADING": "Stage 1: simplify",
        "SIMPLIFY_BLOCK": build_simplify_block(run["simplify"]),
        "CONVERGENT_ITEMS": build_convergent_items(run["findings"]),
        "REVIEWER_CHECKBOXES": build_reviewer_checkboxes(run),
        "FILE_SECTIONS": build_file_sections(run),
        "REVIEWER_ROWS": build_reviewer_rows(run["reviewers"]),
        "TOTAL_FINDINGS": str(len(run["findings"])),
        "GENERATED_AT": esc(run["generated_at"]),
        # Raw <script> string context — validated charset, not escaped.
        "STORAGE_KEY": str(run["storage_key"]),
        "REPO_SLUG": str(run["repo_slug"]),
        "REPORT_FILENAME": str(run["report_filename"]),
        "PRISM_BUNDLE": PRISM_PATH.read_text(encoding="utf-8"),
    }


def render(run: dict) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    subs = build_substitutions(run)

    template_placeholders = set(PLACEHOLDER_RE.findall(template))
    unknown = template_placeholders - set(subs)
    if unknown:
        fail(f"template contains placeholder(s) render.py does not know: {', '.join(sorted(unknown))}")

    # Single pass: substituted values are never re-scanned for placeholders.
    output = PLACEHOLDER_RE.sub(lambda m: subs[m.group(1)], template)

    leftover = sorted({name for name in PLACEHOLDER_RE.findall(output) if name in subs})
    if leftover:
        fail(f"unsubstituted placeholder(s) remain in output: {', '.join(leftover)}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a review-swarm HTML report from run.json")
    parser.add_argument("--input", required=True, help="Path to run.json")
    parser.add_argument("--output", required=True, help="Path to write the report HTML")
    args = parser.parse_args()

    try:
        run = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read {args.input}: {exc}")

    validate_input(run)
    output = render(run)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")
    print(f"render.py: wrote {out_path} ({len(output)} bytes)")


if __name__ == "__main__":
    main()
