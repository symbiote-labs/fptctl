from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import fptctl.commands._options as options

SHOT = {"type": "Shot", "id": 1, "code": "sh010"}


def sent(harness: Any) -> list[tuple[str, dict[str, Any]]]:
    return [(name, kwargs) for name, _, kwargs in harness.client.calls]


def test_create_sends_typed_and_text_values(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["create"] = SHOT
    result = harness.run(
        "create", "Shot", "--set", "code=101", "--set", "sg_cut_in:=101",
        "--set", 'project:={"type": "Project", "id": 70}',
    )  # fmt: skip
    assert (result.code, result.json) == (0, SHOT)
    assert sent(harness) == [
        (
            "create",
            {
                "entity_type": "Shot",
                "data": {
                    "code": "101",
                    "sg_cut_in": 101,
                    "project": {"type": "Project", "id": 70},
                },
            },
        )
    ]


def test_create_with_return_fields_and_data_from_stdin(harness: Any) -> None:
    harness.use_script_env()
    harness.run(
        "create", "Shot", "--data", "-", "--set", "code=b", "--return-fields", "sg_status_list",
        stdin='{"code": "a", "at": {"$datetime": "2026-11-10T14:30:00Z"}}',
    )  # fmt: skip
    assert sent(harness) == [
        (
            "create",
            {
                "entity_type": "Shot",
                "data": {"code": "b", "at": datetime(2026, 11, 10, 14, 30, tzinfo=timezone.utc)},
                "return_fields": ["sg_status_list"],
            },
        )
    ]


def test_create_reads_data_from_a_file(harness: Any, tmp_path: Path) -> None:
    harness.use_script_env()
    path = tmp_path / "data.json"
    path.write_text('{"code": "a"}')
    harness.run("create", "Shot", "--data", f"@{path}")
    assert sent(harness) == [("create", {"entity_type": "Shot", "data": {"code": "a"}})]


@pytest.mark.parametrize(
    "argv",
    [
        ["create", "Shot"],
        ["create", "Shot", "--data", "[1]"],
        ["create", "Shot", "--set", "code"],
        ["update", "Shot", "1"],
        ["update", "Shot", "x", "--set", "code=a"],
        ["update", "Shot", "1", "--set", "code=a", "--multi-entity-mode", "assets=replace"],
        ["update", "Shot", "1", "--set", "code=a", "--multi-entity-mode", "assets"],
    ],
)
def test_write_usage_errors_make_no_call(harness: Any, argv: list[str]) -> None:
    harness.use_script_env()
    result = harness.run(*argv)
    assert result.code == 2
    assert harness.client.calls == []


def test_update_sends_data(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["update"] = SHOT
    result = harness.run("update", "Shot", "1", "--set", "code=sh010")
    assert (result.code, result.json) == (0, SHOT)
    assert sent(harness) == [
        ("update", {"entity_type": "Shot", "entity_id": 1, "data": {"code": "sh010"}})
    ]


def test_update_with_multi_entity_modes(harness: Any) -> None:
    harness.use_script_env()
    harness.run(
        "update", "Shot", "1", "--set", 'assets:=[{"type": "Asset", "id": 2}]',
        "--multi-entity-mode", "assets=add", "--multi-entity-mode", "shots=remove",
    )  # fmt: skip
    assert sent(harness)[0][1]["multi_entity_update_modes"] == {
        "assets": "add",
        "shots": "remove",
    }


@pytest.mark.parametrize(
    ("argv", "record"),
    [
        (
            ["create", "Shot", "--set", "code=a"],
            {
                "call": "create",
                "args": {"entity_type": "Shot", "data": {"code": "a"}, "return_fields": None},
            },
        ),
        (
            ["update", "Shot", "1", "--set", 'at:={"$datetime": "2026-11-10T14:30:00Z"}'],
            {
                "call": "update",
                "args": {
                    "entity_type": "Shot",
                    "entity_id": 1,
                    "data": {"at": "2026-11-10T14:30:00Z"},
                    "multi_entity_update_modes": None,
                },
            },
        ),
        (
            ["delete", "Shot", "1"],
            {"call": "delete", "args": {"entity_type": "Shot", "entity_id": 1}},
        ),
        (
            ["revive", "Shot", "1"],
            {"call": "revive", "args": {"entity_type": "Shot", "entity_id": 1}},
        ),
    ],
)
def test_dry_run_prints_the_call_without_credentials(
    harness: Any, argv: list[str], record: dict[str, Any]
) -> None:
    result = harness.run(*argv, "--dry-run")
    assert (result.code, result.json, result.stderr) == (0, record, "")
    assert harness.built == []
    assert harness.client.calls == []


def test_delete_with_yes(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["delete"] = True
    result = harness.run("delete", "Shot", "1", "--yes")
    assert (result.code, result.json) == (0, True)
    assert sent(harness) == [("delete", {"entity_type": "Shot", "entity_id": 1})]


def test_delete_off_a_tty_without_yes_exits_2(harness: Any) -> None:
    harness.use_script_env()
    result = harness.run("delete", "Shot", "1")
    assert result.code == 2
    assert "--yes" in result.error["message"]
    assert harness.client.calls == []


def test_delete_on_a_tty_asks(harness: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    harness.use_script_env()
    monkeypatch.setattr(options, "interactive", lambda: True)
    harness.client.responses["delete"] = True
    declined = harness.run("delete", "Shot", "1", stdin="n\n")
    assert declined.code == 2
    assert "Delete Shot 1?" in declined.stderr
    assert '"Aborted."' in declined.stderr
    assert harness.client.calls == []
    accepted = harness.run("delete", "Shot", "1", stdin="y\n")
    assert (accepted.code, accepted.stdout) == (0, "true\n")
    assert sent(harness) == [("delete", {"entity_type": "Shot", "entity_id": 1})]


def test_revive(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["revive"] = True
    result = harness.run("revive", "Shot", "1")
    assert (result.code, result.json) == (0, True)
    assert sent(harness) == [("revive", {"entity_type": "Shot", "entity_id": 1})]
