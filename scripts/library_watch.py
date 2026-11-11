"""Check PyPI for a shotgun-api3 release newer than fptctl's pin, and report how its API changed.

    uv run python -m scripts.library_watch          # print the report
    uv run python -m scripts.library_watch --report-dir out  # also write out/report.json
    python -m scripts.library_watch --open-issue out         # check it, open the issue once

The report lists the methods and parameters that were added, removed or changed between the
pinned version and the new one, read from both versions by scripts/api_signatures.py. The
parity inventory turns each of those into burndown items, so this is the to-do list for the
upgrade. The skill skills/fptctl-library-upgrade describes the rest.
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


def _one_line(text: str) -> str:
    """Upstream text on one line: control characters and newlines become spaces."""
    return " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", text).split())


def _fenced(lines: list[str]) -> list[str]:
    """A code block whose fence is longer than any run of backticks in its content, so text
    from the new library can never end the block early and become markdown."""
    longest = max((len(run) for line in lines for run in re.findall(r"`+", line)), default=0)
    fence = "`" * max(3, longest + 1)
    return [f"{fence}text", *lines, fence]


def issue_title(version: str) -> str:
    return f"shotgun-api3 {version} is out"


def render_report(pinned: str, latest: str, diff: ApiDiff) -> str:
    lines = [
        f"shotgun-api3 **{latest}** is on PyPI. fptctl pins **{pinned}**.",
        "",
        f"What changed upstream: [HISTORY.rst]({HISTORY_URL}).",
        "",
        "## Public API changes",
        "",
    ]
    changes = [f"added    {_one_line(name)}" for name in diff.added]
    changes += [f"removed  {_one_line(name)}" for name in diff.removed]
    for name, (before, after) in diff.changed.items():
        changes += [
            f"changed  {_one_line(name)}",
            f"  before {_one_line(before)}",
            f"  after  {_one_line(after)}",
        ]
    lines += _fenced(changes) if changes else ["None: no public method or signature changed."]
    lines += [
        "",
        "## Upgrade",
        "",
        "Follow `skills/fptctl-library-upgrade/SKILL.md`:",
        "",
        f"- [ ] pin `shotgun-api3=={latest}` and update the lock file",
        "- [ ] cover every new burndown item (a command option, or an `api call` case)",
        "- [ ] parity: `burndown --strict` exits 0 at the release commit",
        "- [ ] release with `skills/fptctl-release/SKILL.md`",
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


REPORT_FILE = "report.json"
MAX_REPORT_BYTES = 256 * 1024
MAX_ITEMS = 500
MAX_TEXT = 2000


def report_data(pinned: str, latest: str, diff: ApiDiff) -> dict[str, Any]:
    return {
        "pinned": pinned,
        "latest": latest,
        "added": diff.added,
        "removed": diff.removed,
        "changed": {name: list(pair) for name, pair in diff.changed.items()},
    }


def _text(value: Any) -> str:
    if not isinstance(value, str) or len(value) > MAX_TEXT:
        raise ValueError("report text must be a string of reasonable length")
    return value


def checked_report(raw: bytes, pinned: str, latest: str) -> tuple[str, ApiDiff]:
    """Validate a report written by the job that ran the new library's code.

    That job is untrusted, so nothing it wrote is used as it stands: the versions must match the
    ones this job read itself, the shape must be exact, and the caller renders the issue from the
    validated data.
    """
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError("report is too large")
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != {
        "pinned",
        "latest",
        "added",
        "removed",
        "changed",
    }:
        raise ValueError("report has unexpected keys")
    if data["pinned"] != pinned or data["latest"] != latest:
        raise ValueError("report versions do not match the pin and PyPI")
    added, removed, changed = data["added"], data["removed"], data["changed"]
    if not (isinstance(added, list) and isinstance(removed, list) and isinstance(changed, dict)):
        raise ValueError("report lists have the wrong types")
    if len(added) + len(removed) + len(changed) > MAX_ITEMS:
        raise ValueError("report lists too many changes")
    pairs: dict[str, tuple[str, str]] = {}
    for name, pair in changed.items():
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("a changed signature must be a [before, after] pair")
        pairs[_text(name)] = (_text(pair[0]), _text(pair[1]))
    diff = ApiDiff(
        added=[_text(name) for name in added],
        removed=[_text(name) for name in removed],
        changed=pairs,
    )
    return latest, diff


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watch for shotgun-api3 releases.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--report-dir", type=Path, help=f"also write {REPORT_FILE} there, for --open-issue"
    )
    group.add_argument(
        "--open-issue", type=Path, metavar="DIR", help="open the issue a --report-dir run found"
    )
    args = parser.parse_args(argv)
    pinned = pinned_version(PYPROJECT.read_text(encoding="utf-8"))
    latest = latest_version()
    if version_key(latest) <= version_key(pinned):
        print(f"shotgun-api3 {pinned} is the latest release; nothing to do.")
        return 0
    if args.open_issue is not None:
        # This step holds the token and runs no library code. It re-reads the versions itself
        # and renders the issue from the validated report.
        report_file = args.open_issue / REPORT_FILE
        if not report_file.exists():
            print("No report was handed over; nothing to open.")
            return 1
        version, diff = checked_report(report_file.read_bytes(), pinned, latest)
        print(open_issue(issue_title(version), render_report(pinned, version, diff)))
        return 0
    diff = diff_api(api_of(pinned), api_of(latest))
    print(render_report(pinned, latest, diff))
    if args.report_dir is not None:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        text = json.dumps(report_data(pinned, latest, diff), indent=2)
        (args.report_dir / REPORT_FILE).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
