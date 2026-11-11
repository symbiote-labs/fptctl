import subprocess
from pathlib import Path
from typing import Any

import pytest
from parity.burndown import (
    current_state,
    item_statuses,
    load_waivers,
    render_report,
    run,
)

DIMENSIONS: dict[str, Any] = {
    "surfaces": {"info": "info"},
    "not_exposed": {},
    "filter_operators": {},
    "enums": {},
    "enum_params": {},
}
STATE = {"head": "abc", "clean": True, "parity_hash": "h", "library_version": "3.10.5"}


class Lib:
    def __init__(self, base_url: str) -> None: ...
    def info(self) -> Any: ...
    def close(self) -> None: ...


ITEMS = ["field-read:text", "method:close", "method:info", "param:Shotgun.base_url"]


def case(case_id: str, status: str, covers: list[str], **extra: Any) -> dict[str, Any]:
    return {"id": case_id, "status": status, "covers": covers, "masks": [], "problems": [], **extra}


def results(cases: list[dict[str, Any]], state: dict[str, Any] = STATE) -> dict[str, Any]:
    return {
        "run_id": "20261110T000000Z",
        "state": state,
        "schema": {"data_types": {"text": False}},
        "cases": cases,
    }


def write_waivers(path: Path, *entries: dict[str, str]) -> Path:
    body = "".join(
        "[[waiver]]\n" + "".join(f'{k} = "{v}"\n' for k, v in entry.items()) + "\n"
        for entry in entries
    )
    path.write_text(body)
    return path


def run_with(
    tmp_path: Path,
    cases: list[dict[str, Any]],
    *,
    strict: bool = False,
    waivers: tuple[dict[str, str], ...] = (),
    state: dict[str, Any] = STATE,
    gate: list[str] | None = None,
) -> tuple[int, str]:
    return run(
        strict=strict,
        results=results(cases),
        waivers_path=write_waivers(tmp_path / "waivers.toml", *waivers),
        dimensions=DIMENSIONS,
        cls=Lib,
        state=lambda: state,
        gate=lambda: gate or [],
    )


WAIVE_CLOSE = {"item": "method:close", "reason": "returns None", "evidence": "case close: null"}
ALL_PASS = [
    case("info", "pass", ["method:info", "param:Shotgun.base_url"]),
    case("read", "pass", ["field-read:text"]),
]


def test_status_rules() -> None:
    cases = [
        case("a", "failing", ["method:info"]),
        case("b", "pass", ["method:info"]),
        case("c", "blocked", ["field-read:text"]),
        case("d", "unstable", ["field-read:text"]),
    ]
    statuses = item_statuses(ITEMS, cases, {"method:close": {}}, stale=False)
    assert statuses == {
        "field-read:text": "unstable",
        "method:close": "waived",
        "method:info": "done",
        "param:Shotgun.base_url": "no_case",
    }


def test_stale_only_when_asked() -> None:
    cases = [case("b", "pass", ["method:info"])]
    assert item_statuses(ITEMS, cases, {}, stale=True)["method:info"] == "stale"
    assert item_statuses(ITEMS, cases, {}, stale=True)["method:close"] == "no_case"


def test_waivers_are_validated(tmp_path: Path) -> None:
    good = write_waivers(tmp_path / "w.toml", WAIVE_CLOSE)
    assert load_waivers(good, ITEMS) == {"method:close": WAIVE_CLOSE}
    no_evidence = {k: v for k, v in WAIVE_CLOSE.items() if k != "evidence"}
    with pytest.raises(ValueError, match="evidence"):
        load_waivers(write_waivers(tmp_path / "a.toml", no_evidence), ITEMS)
    with pytest.raises(ValueError, match="not in the inventory"):
        load_waivers(write_waivers(tmp_path / "b.toml", {**WAIVE_CLOSE, "item": "method:x"}), ITEMS)
    with pytest.raises(ValueError, match="more than once"):
        load_waivers(write_waivers(tmp_path / "c.toml", WAIVE_CLOSE, WAIVE_CLOSE), ITEMS)
    assert load_waivers(tmp_path / "missing.toml", ITEMS) == {}


def test_zero_remaining_exits_0(tmp_path: Path) -> None:
    code, report = run_with(tmp_path, ALL_PASS, waivers=(WAIVE_CLOSE,))
    assert code == 0
    assert "returns None" in report and "case close: null" in report


def test_remaining_items_exit_1(tmp_path: Path) -> None:
    code, report = run_with(tmp_path, ALL_PASS)
    assert code == 1
    assert "method:close" in report


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"state": {**STATE, "head": "def"}}, "do not match"),
        ({"state": {**STATE, "clean": False}}, "not clean"),
        ({"gate": ["uv run mypy src parity"]}, "mypy"),
    ],
)
def test_strict_needs_fresh_results_and_a_green_gate(
    tmp_path: Path, kwargs: dict[str, Any], reason: str
) -> None:
    code, report = run_with(tmp_path, ALL_PASS, strict=True, waivers=(WAIVE_CLOSE,), **kwargs)
    assert code == 1
    assert reason in report


def test_strict_passes_when_everything_matches(tmp_path: Path) -> None:
    assert run_with(tmp_path, ALL_PASS, strict=True, waivers=(WAIVE_CLOSE,))[0] == 0


def test_no_results_exits_1(tmp_path: Path) -> None:
    code, report = run(
        strict=False,
        results=None,
        waivers_path=tmp_path / "w.toml",
        dimensions=DIMENSIONS,
        cls=Lib,
        state=lambda: STATE,
        gate=lambda: [],
    )
    assert code == 1
    assert "parity.runner" in report


def test_report_lists_masks_and_problems() -> None:
    cases = [
        case("w", "pass", ["method:info"], masks=["id", "created_at"]),
        case("x", "failing", ["method:close"], problems=["$.a: direct 1, CLI 2"]),
    ]
    statuses = item_statuses(ITEMS, cases, {}, stale=False)
    report = render_report(statuses, cases, {}, results(cases))
    assert "created_at" in report and "`w`" in report
    assert "$.a: direct 1, CLI 2" in report


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_current_state_tracks_parity_files(tmp_path: Path) -> None:
    (tmp_path / "parity").mkdir()
    (tmp_path / "parity" / "runner.py").write_text("x = 1\n")
    (tmp_path / "parity" / "waivers.toml").write_text("")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", ".")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x")
    first = current_state(tmp_path)
    assert first["clean"] is True and len(first["head"]) == 40
    (tmp_path / "parity" / "waivers.toml").write_text("# changed\n")
    second = current_state(tmp_path)
    assert second["clean"] is False
    assert second["parity_hash"] != first["parity_hash"]
