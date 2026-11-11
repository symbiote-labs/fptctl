import inspect
import re
from typing import Any

import pytest
import shotgun_api3
from parity.inventory import public_methods
from scripts import library_watch
from scripts.api_signatures import signatures

from fpt import __version__

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
    tags = set(re.findall(r"fpt-cli@v([0-9.]+)", readme))
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


def test_report_keeps_upstream_backticks_out_of_code_spans() -> None:
    diff = library_watch.ApiDiff(changed={"find": ("(a)", "(a, b='`x`')")})

    report = library_watch.render_report("1.0.0", "1.0.1", diff)

    assert "(a, b=''x'')" in report
