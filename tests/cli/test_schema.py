from pathlib import Path
from typing import Any

import pytest

import fpt.commands._options as options

PROJECT = {"type": "Project", "id": 70}


def sent(harness: Any) -> list[tuple[str, dict[str, Any]]]:
    return [(name, kwargs) for name, _, kwargs in harness.client.calls]


@pytest.mark.parametrize(
    ("argv", "call"),
    [
        (["schema", "entities"], ("schema_entity_read", {})),
        (
            ["schema", "entities", "--project", "Project:70"],
            ("schema_entity_read", {"project_entity": PROJECT}),
        ),
        (["schema", "read"], ("schema_read", {})),
        (
            ["schema", "read", "--project", '{"type": "Project", "id": 70}'],
            ("schema_read", {"project_entity": PROJECT}),
        ),
        (["schema", "fields", "Shot"], ("schema_field_read", {"entity_type": "Shot"})),
        (
            ["schema", "fields", "Shot", "code", "--project", "Project:70"],
            (
                "schema_field_read",
                {"entity_type": "Shot", "field_name": "code", "project_entity": PROJECT},
            ),
        ),
    ],
)
def test_schema_reads(harness: Any, argv: list[str], call: tuple[str, dict[str, Any]]) -> None:
    harness.use_script_env()
    harness.client.responses[call[0]] = {"Shot": {"name": "Shot"}}
    result = harness.run(*argv)
    assert (result.code, result.json) == (0, {"Shot": {"name": "Shot"}})
    assert sent(harness) == [call]


def test_field_create(harness: Any, tmp_path: Path) -> None:
    harness.use_script_env()
    harness.client.responses["schema_field_create"] = "sg_scratch"
    result = harness.run("schema", "field-create", "Shot", "text", "Scratch")
    assert (result.code, result.json) == (0, "sg_scratch")
    path = tmp_path / "props.json"
    path.write_text('{"description": "d"}')
    harness.run("schema", "field-create", "Shot", "text", "Scratch", "--properties", f"@{path}")
    base = {"entity_type": "Shot", "data_type": "text", "display_name": "Scratch"}
    assert sent(harness) == [
        ("schema_field_create", base),
        ("schema_field_create", {**base, "properties": {"description": "d"}}),
    ]


def test_field_update(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["schema_field_update"] = True
    result = harness.run(
        "schema", "field-update", "Shot", "sg_x", "--properties", "-", "--project", "Project:70",
        stdin='{"visible": false}',
    )  # fmt: skip
    assert (result.code, result.json) == (0, True)
    assert sent(harness) == [
        (
            "schema_field_update",
            {
                "entity_type": "Shot",
                "field_name": "sg_x",
                "properties": {"visible": False},
                "project_entity": PROJECT,
            },
        )
    ]


@pytest.mark.parametrize(
    "argv",
    [
        ["schema", "field-update", "Shot", "sg_x"],
        ["schema", "field-update", "Shot", "sg_x", "--properties", "[1]"],
        ["schema", "field-create", "Shot", "text", "X", "--properties", "{nope"],
        ["schema", "fields", "Shot", "--project", "70"],
        ["schema", "read", "--project", "x"],
    ],
)
def test_schema_usage_errors(harness: Any, argv: list[str]) -> None:
    harness.use_script_env()
    assert harness.run(*argv).code == 2
    assert harness.client.calls == []


def test_field_delete_needs_yes_off_a_tty(harness: Any) -> None:
    harness.use_script_env()
    result = harness.run("schema", "field-delete", "Shot", "sg_x")
    assert result.code == 2
    assert "--yes" in result.error["message"]
    assert harness.client.calls == []
    harness.client.responses["schema_field_delete"] = True
    assert harness.run("schema", "field-delete", "Shot", "sg_x", "--yes").json is True
    assert sent(harness) == [("schema_field_delete", {"entity_type": "Shot", "field_name": "sg_x"})]


def test_field_delete_on_a_tty_asks(harness: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    harness.use_script_env()
    monkeypatch.setattr(options, "interactive", lambda: True)
    declined = harness.run("schema", "field-delete", "Shot", "sg_x", stdin="n\n")
    assert declined.code == 2
    assert "Delete field Shot.sg_x?" in declined.stderr
    assert harness.client.calls == []


@pytest.mark.parametrize(
    ("argv", "call", "args"),
    [
        (
            ["field-create", "Shot", "text", "X"],
            "schema_field_create",
            {"entity_type": "Shot", "data_type": "text", "display_name": "X", "properties": None},
        ),
        (
            ["field-update", "Shot", "sg_x", "--properties", '{"a": 1}'],
            "schema_field_update",
            {
                "entity_type": "Shot",
                "field_name": "sg_x",
                "properties": {"a": 1},
                "project_entity": None,
            },
        ),
        (
            ["field-delete", "Shot", "sg_x"],
            "schema_field_delete",
            {"entity_type": "Shot", "field_name": "sg_x"},
        ),
    ],
)
def test_schema_writes_dry_run(
    harness: Any, argv: list[str], call: str, args: dict[str, Any]
) -> None:
    result = harness.run("schema", *argv, "--dry-run")
    assert (result.code, result.json) == (0, {"call": call, "args": args})
    assert harness.built == []
