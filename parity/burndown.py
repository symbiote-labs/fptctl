"""The burndown: inventory joined with the latest parity results and the waivers.

`uv run python -m parity.burndown --strict` exits 0 only when nothing remains, the results match the
current state, and the gate is green (spec, "Definition of done").
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from parity.inventory import compute_items, load_dimensions

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "parity" / "results"
LATEST = RESULTS_DIR / "latest.json"
WAIVERS_PATH = REPO_ROOT / "parity" / "waivers.toml"
REPORT_PATH = REPO_ROOT / "BURNDOWN.md"

REMAINING = ("no_case", "failing", "unstable", "blocked", "stale")
_FAILURES = ("failing", "unstable", "blocked")
_WAIVER_FIELDS = ("item", "reason", "evidence")
GATE_COMMANDS = (
    ("uv", "run", "ruff", "format", "--check", "."),
    ("uv", "run", "ruff", "check", "."),
    ("uv", "run", "mypy", "src", "parity"),
    ("uv", "run", "pytest", "-q"),
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def current_state(root: Path = REPO_ROOT) -> dict[str, Any]:
    """What a parity run's results must match to count under --strict."""
    import shotgun_api3

    parity = root / "parity"
    files = sorted(parity.glob("*.py")) + [parity / "dimensions.toml", parity / "waivers.toml"]
    digest = hashlib.sha256()
    for path in files:
        if path.exists():
            digest.update(path.relative_to(root).as_posix().encode() + b"\0")
            digest.update(path.read_bytes() + b"\0")
    return {
        "head": _git(root, "rev-parse", "HEAD"),
        "clean": _git(root, "status", "--porcelain") == "",
        "parity_hash": digest.hexdigest(),
        "library_version": shotgun_api3.__version__,
    }


def load_waivers(path: Path, items: Sequence[str]) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    known = set(items)
    waivers: dict[str, dict[str, str]] = {}
    for entry in tomllib.loads(path.read_text(encoding="utf-8")).get("waiver", []):
        missing = [name for name in _WAIVER_FIELDS if not entry.get(name)]
        if missing:
            raise ValueError(f"{path}: a waiver is missing {', '.join(missing)}: {entry}")
        item = entry["item"]
        if item not in known:
            raise ValueError(f"{path}: waived item {item} is not in the inventory")
        if item in waivers:
            raise ValueError(f"{path}: {item} is waived more than once")
        waivers[item] = {name: entry[name] for name in _WAIVER_FIELDS}
    return waivers


def item_statuses(
    items: Sequence[str],
    cases: Sequence[Mapping[str, Any]],
    waivers: Mapping[str, Any],
    *,
    stale: bool,
) -> dict[str, str]:
    touched: dict[str, set[str]] = {}
    for case in cases:
        for item in case["covers"]:
            touched.setdefault(item, set()).add(case["status"])
    statuses: dict[str, str] = {}
    for item in items:
        if item in waivers:
            statuses[item] = "waived"
        elif item not in touched:
            statuses[item] = "no_case"
        elif stale:
            statuses[item] = "stale"
        elif "pass" in touched[item]:
            statuses[item] = "done"
        else:
            statuses[item] = next(s for s in _FAILURES if s in touched[item])
    return statuses


def counts(statuses: Mapping[str, str]) -> dict[str, int]:
    found = Counter(statuses.values())
    return {name: found[name] for name in ("done", "waived", *REMAINING)}


def render_report(
    statuses: Mapping[str, str],
    cases: Sequence[Mapping[str, Any]],
    waivers: Mapping[str, Mapping[str, str]],
    results: Mapping[str, Any],
) -> str:
    totals = counts(statuses)
    remaining = sum(totals[name] for name in REMAINING)
    lines = [
        "# Burndown",
        "",
        f"Run `{results.get('run_id')}`. Items: {len(statuses)}. Remaining: **{remaining}**.",
        "",
        "| Status | Items |",
        "|---|---|",
        *(f"| {name} | {count} |" for name, count in totals.items()),
        "",
        f"## Waivers ({len(waivers)})",
        "",
    ]
    for item, waiver in sorted(waivers.items()):
        lines += [
            f"- `{item}`",
            f"  - reason: {waiver['reason']}",
            f"  - evidence: {waiver['evidence']}",
        ]
    masked = [case for case in cases if case.get("masks")]
    lines += ["", f"## Masks in use ({len(masked)} cases)", ""]
    lines += [f"- `{case['id']}`: {', '.join(case['masks'])}" for case in masked]
    troubled = [case for case in cases if case["status"] != "pass"]
    lines += ["", f"## Cases that did not pass ({len(troubled)})", ""]
    for case in troubled:
        lines.append(f"- `{case['id']}` ({case['status']})")
        lines += [f"  - {problem}" for problem in case.get("problems", [])]
    lines += ["", "## Remaining items", ""]
    for name in REMAINING:
        names = sorted(item for item, status in statuses.items() if status == name)
        if names:
            lines += [f"### {name} ({len(names)})", "", *(f"- `{item}`" for item in names), ""]
    return "\n".join(lines) + "\n"


def gate_failures(root: Path = REPO_ROOT) -> list[str]:
    failed = []
    for command in GATE_COMMANDS:
        if subprocess.run(command, cwd=root, capture_output=True).returncode != 0:
            failed.append(" ".join(command))
    return failed


def run(
    *,
    strict: bool,
    results: Mapping[str, Any] | None,
    waivers_path: Path,
    dimensions: Mapping[str, Any],
    cls: type,
    state: Callable[[], Mapping[str, Any]],
    gate: Callable[[], list[str]],
) -> tuple[int, str]:
    if results is None:
        return 1, "No parity results. Run `uv run python -m parity.runner` first.\n"
    items = compute_items(cls, results["schema"]["data_types"], dimensions)
    waivers = load_waivers(waivers_path, items)
    problems: list[str] = []
    stale = False
    if strict:
        current = state()
        if not current["clean"]:
            stale = True
            problems.append("The working tree is not clean.")
        elif dict(results["state"]) != dict(current):
            stale = True
            problems.append(
                f"The results do not match the current state: {json.dumps(results['state'])} "
                f"vs {json.dumps(dict(current))}."
            )
        problems += [f"Gate command failed: `{command}`" for command in gate()]
    statuses = item_statuses(items, results["cases"], waivers, stale=stale)
    report = render_report(statuses, results["cases"], waivers, results)
    if problems:
        report += "\n## Strict check\n\n" + "".join(f"- {p}\n" for p in problems)
    remaining = sum(counts(statuses)[name] for name in REMAINING)
    return (0 if remaining == 0 and not problems else 1), report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m parity.burndown")
    parser.add_argument(
        "--strict", action="store_true", help="also require fresh results and a green gate"
    )
    options = parser.parse_args(argv)
    import shotgun_api3

    results = json.loads(LATEST.read_text(encoding="utf-8")) if LATEST.exists() else None
    code, report = run(
        strict=options.strict,
        results=results,
        waivers_path=WAIVERS_PATH,
        dimensions=load_dimensions(),
        cls=shotgun_api3.Shotgun,
        state=current_state,
        gate=gate_failures,
    )
    REPORT_PATH.write_text(report, encoding="utf-8")
    summary = report.split("## Waivers")[0].strip()
    print(summary)
    print(f"\nFull report: {REPORT_PATH}. Exit {code}.")
    return code


if __name__ == "__main__":
    sys.exit(main())
