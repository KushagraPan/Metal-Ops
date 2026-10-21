#!/usr/bin/env python3
"""Publish _docs/backlog.md to GitHub as issues.

The backlog file is the source; this script mirrors each `## #N [P0|P1] title`
section into one issue, preserving the body verbatim (acceptance criteria and
tests included). It is safe to re-run: issues whose title already exists are
skipped.

Usage:
    python scripts/create_issues.py --dry-run
    python scripts/create_issues.py
    python scripts/create_issues.py --repo owner/name

Requires the GitHub CLI (`gh`) and an authenticated session.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

BACKLOG = Path(__file__).resolve().parent.parent / "_docs" / "backlog.md"

SECTION_RE = re.compile(r"^## #(?P<num>\d+) \[(?P<priority>P[01])\] (?P<title>.+)$")
LABELS_RE = re.compile(r"^Labels:\s*(?P<labels>.+?)(?:\s*·\s*Depends on:\s*(?P<deps>.+))?$")

LABEL_COLORS = {
    "setup": "6b7280",
    "backend": "1d4ed8",
    "database": "7c3aed",
    "calc": "0e7490",
    "frontend": "0891b2",
    "storage": "b45309",
    "testing": "15803d",
    "devops": "374151",
    "observability": "9d174d",
    "agent": "7e22ce",
    "docs": "0369a1",
    "design": "db2777",
    "security": "b91c1c",
}


@dataclass
class Issue:
    number: int
    priority: str
    title: str
    body: str
    labels: list[str] = field(default_factory=list)
    depends_on: str = "none"

    @property
    def full_title(self) -> str:
        # Title format required by the backlog: "[P0] #N title"
        return f"[{self.priority}] #{self.number} {self.title}"


def parse_backlog(text: str) -> list[Issue]:
    lines = text.splitlines()
    starts = [
        (i, m)
        for i, line in enumerate(lines)
        if (m := SECTION_RE.match(line))
    ]
    if not starts:
        raise SystemExit(f"No '## #N [P0|P1] title' sections found in {BACKLOG}")

    issues: list[Issue] = []
    for index, (start, match) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(lines)
        body_lines = lines[start + 1 : end]

        # Drop the horizontal rule that separates sections, and surrounding blanks.
        while body_lines and body_lines[0].strip() == "":
            body_lines.pop(0)
        while body_lines and body_lines[-1].strip() in {"", "---"}:
            body_lines.pop()

        issue = Issue(
            number=int(match.group("num")),
            priority=match.group("priority"),
            title=match.group("title").strip(),
            body="\n".join(body_lines).strip() + "\n",
        )

        for line in body_lines:
            labels_match = LABELS_RE.match(line.strip())
            if labels_match:
                raw = labels_match.group("labels")
                issue.labels = [p.strip() for p in raw.split("·") if p.strip()]
                issue.depends_on = (labels_match.group("deps") or "none").strip()
                break

        issues.append(issue)

    return issues


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def require_gh() -> None:
    try:
        result = run(["gh", "auth", "status"], check=False)
    except FileNotFoundError:
        raise SystemExit("GitHub CLI 'gh' is not installed or not on PATH.")
    if result.returncode != 0:
        raise SystemExit(
            "GitHub CLI is not authenticated. Run `gh auth login`, then retry.\n"
            + (result.stderr or result.stdout).strip()
        )


def ensure_labels(labels: set[str]) -> None:
    for label in sorted(labels):
        run(
            [
                "gh",
                "label",
                "create",
                label,
                "--color",
                LABEL_COLORS.get(label, "6b7280"),
                "--force",
            ],
            check=False,
        )


def existing_titles(repo: str | None) -> set[str]:
    args = ["gh", "issue", "list", "--state", "all", "--limit", "500", "--json", "title"]
    if repo:
        args += ["--repo", repo]
    result = run(args)
    import json

    return {item["title"] for item in json.loads(result.stdout or "[]")}


def create_issue(issue: Issue, repo: str | None) -> str:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(issue.body)
        body_path = handle.name

    args = ["gh", "issue", "create", "--title", issue.full_title, "--body-file", body_path]
    for label in issue.labels:
        args += ["--label", label]
    if repo:
        args += ["--repo", repo]

    try:
        result = run(args)
    finally:
        Path(body_path).unlink(missing_ok=True)

    return result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="parse and print, do not call GitHub")
    parser.add_argument("--repo", help="owner/name; defaults to the current directory's repository")
    args = parser.parse_args()

    issues = parse_backlog(BACKLOG.read_text(encoding="utf-8"))

    if args.dry_run:
        print(f"Parsed {len(issues)} issues from {BACKLOG}\n")
        for issue in issues:
            labels = ", ".join(issue.labels) or "(none)"
            print(f"  {issue.full_title}")
            print(f"      labels: {labels} · depends on: {issue.depends_on}")
            print(f"      body: {len(issue.body)} chars")
        return 0

    require_gh()
    all_labels = {label for issue in issues for label in issue.labels}
    ensure_labels(all_labels)

    seen = existing_titles(args.repo)
    created = skipped = 0

    for issue in issues:
        if issue.full_title in seen:
            print(f"skip     {issue.full_title}")
            skipped += 1
            continue
        url = create_issue(issue, args.repo)
        print(f"created  {issue.full_title}  {url}")
        created += 1

    print(f"\n{created} created, {skipped} skipped, {len(issues)} in backlog.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
