"""Check PyPI for a shotgun-api3 release newer than fpt's pin, and report how its API changed.

    uv run python -m scripts.library_watch          # print the report
    uv run python -m scripts.library_watch --issue  # also open a GitHub issue, once per version

The report lists the methods and parameters that were added, removed or changed between the
pinned version and the new one, read from both versions by scripts/api_signatures.py. The
parity inventory turns each of those into burndown items, so this is the to-do list for the
upgrade. The skill skills/fpt-library-upgrade describes the rest.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
API_SIGNATURES = ROOT / "scripts" / "api_signatures.py"
PYPI_URL = "https://pypi.org/pypi/shotgun-api3/json"
HISTORY_URL = "https://github.com/shotgunsoftware/python-api/blob/master/HISTORY.rst"
PIN = re.compile(r'"shotgun-api3==([^"]+)"')


def pinned_version(pyproject_text: str) -> str:
    match = PIN.search(pyproject_text)
    if match is None:
        raise ValueError("pyproject.toml does not pin shotgun-api3 with ==")
    return match.group(1)


def version_key(version: str) -> tuple[int, ...]:
    """3.10.5 -> (3, 10, 5). A pre-release (any non-numeric part) is not a release to follow."""
    parts = version.split(".")
    if not all(part.isdigit() for part in parts):
        raise ValueError(f"not a final release: {version}")
    return tuple(int(part) for part in parts)


def latest_version() -> str:
    with urllib.request.urlopen(PYPI_URL, timeout=30) as response:  # noqa: S310 (fixed https URL)
        return str(json.load(response)["info"]["version"])


TOKEN_VARIABLES = ("GH_TOKEN", "GITHUB_TOKEN")


def api_of(version: str) -> dict[str, Any]:
    """The public API of one library version, from a throw-away environment.

    Installing and importing a new release runs code nobody has reviewed yet, so the GitHub
    token the workflow holds for opening the issue is kept out of that process.
    """
    command = [
        "uv", "run", "--no-project", "--quiet", "--with", f"shotgun-api3=={version}",
        "python", str(API_SIGNATURES),
    ]  # fmt: skip
    env = {name: value for name, value in os.environ.items() if name not in TOKEN_VARIABLES}
    output = subprocess.run(command, check=True, capture_output=True, text=True, env=env).stdout
    api: dict[str, Any] = json.loads(output)
    return api


@dataclass(frozen=True)
class ApiDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: dict[str, tuple[str, str]] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


def diff_api(old: dict[str, Any], new: dict[str, Any]) -> ApiDiff:
    old_methods, new_methods = old["methods"], new["methods"]
    changed = {
        name: (old_methods[name]["signature"], new_methods[name]["signature"])
        for name in sorted(set(old_methods) & set(new_methods))
        if old_methods[name]["signature"] != new_methods[name]["signature"]
    }
    if old["constructor"]["signature"] != new["constructor"]["signature"]:
        changed["Shotgun (constructor)"] = (
            old["constructor"]["signature"],
            new["constructor"]["signature"],
        )
    return ApiDiff(
        added=sorted(set(new_methods) - set(old_methods)),
        removed=sorted(set(old_methods) - set(new_methods)),
        changed=changed,
    )


def _code(text: str) -> str:
    """Text for a markdown code span: a backtick from upstream would end the span early."""
    return text.replace("`", "'")


def issue_title(version: str) -> str:
    return f"shotgun-api3 {version} is out"


def render_report(pinned: str, latest: str, diff: ApiDiff) -> str:
    lines = [
        f"shotgun-api3 **{latest}** is on PyPI. fpt pins **{pinned}**.",
        "",
        f"What changed upstream: [HISTORY.rst]({HISTORY_URL}).",
        "",
        "## Public API changes",
        "",
    ]
    if diff.empty:
        lines.append("None: no public method or signature changed.")
    for name in diff.added:
        lines.append(f"- added `{_code(name)}`")
    for name in diff.removed:
        lines.append(f"- removed `{_code(name)}`")
    for name, (before, after) in diff.changed.items():
        lines.append(f"- changed `{_code(name)}`: `{_code(before)}` -> `{_code(after)}`")
    lines += [
        "",
        "## Upgrade",
        "",
        "Follow `skills/fpt-library-upgrade/SKILL.md`:",
        "",
        f"- [ ] pin `shotgun-api3=={latest}` and update the lock file",
        "- [ ] cover every new burndown item (a command option, or an `api call` case)",
        "- [ ] parity: `burndown --strict` exits 0 at the release commit",
        "- [ ] release with `skills/fpt-release/SKILL.md`",
    ]
    return "\n".join(lines) + "\n"


def open_issue(title: str, body: str) -> str:
    """Open the issue unless one with this exact title exists. Returns what happened."""
    listed = subprocess.run(
        ["gh", "issue", "list", "--state", "all", "--search", f'"{title}" in:title',
         "--json", "title,url"],
        check=True, capture_output=True, text=True,
    ).stdout  # fmt: skip
    for issue in json.loads(listed):
        if issue["title"] == title:
            return f"already open: {issue['url']}"
    created = subprocess.run(
        ["gh", "issue", "create", "--title", title, "--body-file", "-"],
        input=body, check=True, capture_output=True, text=True,
    ).stdout  # fmt: skip
    return f"opened: {created.strip()}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watch for shotgun-api3 releases.")
    parser.add_argument("--issue", action="store_true", help="open a GitHub issue for it")
    args = parser.parse_args(argv)
    pinned = pinned_version(PYPROJECT.read_text(encoding="utf-8"))
    latest = latest_version()
    if version_key(latest) <= version_key(pinned):
        print(f"shotgun-api3 {pinned} is the latest release; nothing to do.")
        return 0
    report = render_report(pinned, latest, diff_api(api_of(pinned), api_of(latest)))
    print(report)
    if args.issue:
        print(open_issue(issue_title(latest), report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
