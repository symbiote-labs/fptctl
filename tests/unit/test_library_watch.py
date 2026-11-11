import inspect
import json
import re
from pathlib import Path
from typing import Any

import pytest
import shotgun_api3
from parity.inventory import public_methods
from scripts import library_watch
from scripts.api_signatures import signatures

from fptctl import __version__

ROOT = library_watch.ROOT


def api(methods: dict[str, str], constructor: str = "(base_url)") -> dict[str, Any]:
    return {
        "constructor": {"signature": constructor},
        "methods": {name: {"signature": signature} for name, signature in methods.items()},
    }


def test_pinned_version_reads_the_exact_pin() -> None:
    assert library_watch.pinned_version('deps = ["shotgun-api3==3.10.5"]') == "3.10.5"


def test_pinned_version_refuses_a_range() -> None:
    with pytest.raises(ValueError, match="does not pin"):
        library_watch.pinned_version('deps = ["shotgun-api3>=3.10.5"]')


@pytest.mark.parametrize(
    ("newer", "older"),
    [("3.10.6", "3.10.5"), ("3.11.0", "3.10.9"), ("3.10.10", "3.10.9")],
    ids=["patch", "minor", "two-digit-patch"],
)
def test_version_key_orders_releases_numerically(newer: str, older: str) -> None:
    assert library_watch.version_key(newer) > library_watch.version_key(older)


def test_version_key_refuses_a_pre_release() -> None:
    with pytest.raises(ValueError, match="not a final release"):
        library_watch.version_key("3.11.0rc1")


def test_diff_api_reports_added_removed_and_changed_methods() -> None:
    old = api({"find": "(entity_type)", "close": "()", "info": "()"})
    new = api({"find": "(entity_type, limit=0)", "info": "()", "export": "()"}, "(base_url, x=1)")

    diff = library_watch.diff_api(old, new)

    assert diff.added == ["export"]
    assert diff.removed == ["close"]
    assert diff.changed == {
        "find": ("(entity_type)", "(entity_type, limit=0)"),
        "Shotgun (constructor)": ("(base_url)", "(base_url, x=1)"),
    }


def test_report_says_when_nothing_changed() -> None:
    report = library_watch.render_report("3.10.5", "3.10.6", library_watch.ApiDiff())
    assert "None: no public method or signature changed." in report
    assert "pin `shotgun-api3==3.10.6`" in report


def test_api_signatures_counts_the_methods_the_parity_inventory_counts() -> None:
    dumped = signatures()

    inventory = public_methods(shotgun_api3.Shotgun)

    assert set(dumped["methods"]) == set(inventory), "the watch and the inventory disagree"
    assert dumped["constructor"]["params"] == [
        name for name in inspect.signature(shotgun_api3.Shotgun).parameters if name != "self"
    ]


def test_readme_names_the_pinned_library_version_and_the_current_release() -> None:
    pinned = library_watch.pinned_version((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert f"`shotgun_api3` {pinned}" in readme, "README must name the pinned library version"
    tags = set(re.findall(r"fptctl@v([0-9.]+)", readme))
    assert tags == {__version__}, f"README install lines point at {tags}, not v{__version__}"


def test_api_of_keeps_github_tokens_away_from_the_new_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        seen.update(kwargs)
        return type("Done", (), {"stdout": '{"methods": {}, "constructor": {}}'})()

    monkeypatch.setenv("GH_TOKEN", "secret")
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setattr(library_watch.subprocess, "run", fake_run)

    library_watch.api_of("9.9.9")

    assert "GH_TOKEN" not in seen["env"] and "GITHUB_TOKEN" not in seen["env"]
    assert "PATH" in seen["env"], "the rest of the environment still reaches uv"


def test_report_fences_upstream_text_so_it_cannot_become_markdown() -> None:
    hostile = "(a, b='```')\n## Injected heading\n[click](https://example.com)"
    diff = library_watch.ApiDiff(changed={"find": ("(a)", hostile)})

    report = library_watch.render_report("1.0.0", "1.0.1", diff)

    assert "\n## Injected heading" not in report, "a newline from upstream started a heading"
    assert "````text" in report, "the fence must be longer than the longest backtick run"
    assert "  after  (a, b='```') ## Injected heading [click](https://example.com)" in report


def test_report_dir_then_open_issue_renders_the_issue_in_the_trusted_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(library_watch, "latest_version", lambda: "3.10.6")
    monkeypatch.setattr(library_watch, "api_of", lambda version: api({"find": f"({version})"}))
    opened: list[tuple[str, str]] = []
    monkeypatch.setattr(library_watch, "open_issue", lambda t, b: opened.append((t, b)) or "ok")

    library_watch.main(["--report-dir", str(tmp_path)])
    library_watch.main(["--open-issue", str(tmp_path)])

    assert opened[0][0] == "shotgun-api3 3.10.6 is out"
    assert "fptctl pins **3.10.5**" in opened[0][1]
    assert "  after  (3.10.6)" in opened[0][1]


def report(**changes: Any) -> bytes:
    data: dict[str, Any] = {
        "pinned": "3.10.5", "latest": "3.10.6", "added": [], "removed": [], "changed": {},
    }  # fmt: skip
    data.update(changes)
    return json.dumps(data).encode()


@pytest.mark.parametrize(
    "raw",
    [
        report(latest="3.10.9"),
        report(pinned="3.9.0"),
        report(extra="x"),
        report(added="find"),
        report(changed={"find": ["(a)"]}),
        report(added=["x" * 3000]),
        b"x" * (library_watch.MAX_REPORT_BYTES + 1),
    ],
    ids=["other-latest", "other-pin", "extra-key", "added-not-a-list", "bad-pair", "long-text",
         "too-big"],
)  # fmt: skip
def test_checked_report_rejects_anything_the_untrusted_job_could_tamper_with(raw: bytes) -> None:
    with pytest.raises(ValueError):
        library_watch.checked_report(raw, "3.10.5", "3.10.6")


def test_checked_report_accepts_a_well_formed_report() -> None:
    version, diff = library_watch.checked_report(
        report(added=["export"], changed={"find": ["(a)", "(a, b)"]}), "3.10.5", "3.10.6"
    )

    assert version == "3.10.6"
    assert diff.added == ["export"] and diff.changed == {"find": ("(a)", "(a, b)")}


def test_open_issue_fails_when_the_report_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(library_watch, "latest_version", lambda: "3.10.6")

    assert library_watch.main(["--open-issue", str(tmp_path)]) == 1
