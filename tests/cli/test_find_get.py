from pathlib import Path
from typing import Any

import pytest

SHOT = {"type": "Shot", "id": 1, "code": "sh010"}


def sent(harness: Any) -> list[tuple[str, dict[str, Any]]]:
    return [(name, kwargs) for name, _, kwargs in harness.client.calls]


def test_find_with_no_options_sends_only_the_type_and_empty_filters(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["find"] = [SHOT]
    result = harness.run("find", "Shot")
    assert (result.code, result.json) == (0, [SHOT])
    assert sent(harness) == [("find", {"entity_type": "Shot", "filters": []})]


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["-f", "code is sh010"], {"filters": [["code", "is", "sh010"]]}),
        (
            ["-f", "code is sh010", "-f", "id greater_than 3"],
            {"filters": [["code", "is", "sh010"], ["id", "greater_than", 3]]},
        ),
        (
            ["-f", "code is a", "-f", "code is b", "--any"],
            {"filters": [["code", "is", "a"], ["code", "is", "b"]], "filter_operator": "any"},
        ),
        (
            ["--filters", '{"filter_operator": "all", "filters": [["id", "is", 1]]}'],
            {"filters": {"filter_operator": "all", "filters": [["id", "is", 1]]}},
        ),
        (["--fields", "code,sg_status_list"], {"fields": ["code", "sg_status_list"]}),
        (
            ["--order", "code,-id"],
            {
                "order": [
                    {"field_name": "code", "direction": "asc"},
                    {"field_name": "id", "direction": "desc"},
                ]
            },
        ),
        (["--limit", "5"], {"limit": 5}),
        (["--limit", "5", "--page", "2"], {"limit": 5, "page": 2}),
        (["--retired-only"], {"retired_only": True}),
        (["--include-archived-projects", "false"], {"include_archived_projects": False}),
        (["--include-archived-projects", "true"], {"include_archived_projects": True}),
        (
            ["--additional-filter-presets", '[{"preset_name": "NAVIGATION_FILTER"}]'],
            {"additional_filter_presets": [{"preset_name": "NAVIGATION_FILTER"}]},
        ),
    ],
)
def test_find_passes_each_option(harness: Any, argv: list[str], expected: dict[str, Any]) -> None:
    harness.use_script_env()
    harness.client.responses["find"] = [SHOT]
    assert harness.run("find", "Shot", *argv).code == 0
    assert sent(harness) == [("find", {"entity_type": "Shot", "filters": [], **expected})]


def test_find_reads_filters_from_a_file_and_stdin(harness: Any, tmp_path: Path) -> None:
    harness.use_script_env()
    path = tmp_path / "filters.json"
    path.write_text('[["id", "is", 1]]')
    harness.run("find", "Shot", "--filters", f"@{path}")
    harness.run("find", "Shot", "--filters", "-", stdin='[["id", "is", 2]]')
    assert [kwargs["filters"] for _, kwargs in sent(harness)] == [
        [["id", "is", 1]],
        [["id", "is", 2]],
    ]


@pytest.mark.parametrize(
    "argv",
    [
        ["--filters", "[]", "-f", "id is 1"],
        ["--filters", "[]", "--any"],
        ["-f", "id"],
        ["--filters", "{nope"],
        ["--include-archived-projects", "maybe"],
        ["--limit", "x"],
        ["--fields", "a,,b"],
    ],
)
def test_find_usage_errors_make_no_call(harness: Any, argv: list[str]) -> None:
    harness.use_script_env()
    result = harness.run("find", "Shot", *argv)
    assert result.code == 2
    assert result.error["type"] == "usage"
    assert harness.client.calls == []


def test_find_as_a_table(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["find"] = [SHOT]
    result = harness.run("--format", "table", "find", "Shot")
    assert result.code == 0
    assert "sh010" in result.stdout and "code" in result.stdout


def test_get_is_find_one_with_an_id_filter(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["find_one"] = SHOT
    result = harness.run("get", "Shot", "1")
    assert (result.code, result.json) == (0, SHOT)
    assert sent(harness) == [("find_one", {"entity_type": "Shot", "filters": [["id", "is", 1]]})]


def test_get_passes_each_option(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["find_one"] = SHOT
    argv = [
        "--fields", "code", "--order", "-code", "--any", "--retired-only",
        "--include-archived-projects", "false",
        "--additional-filter-presets", '[{"preset_name": "NAVIGATION_FILTER"}]',
    ]  # fmt: skip
    assert harness.run("get", "Shot", "1", *argv).code == 0
    assert sent(harness) == [
        (
            "find_one",
            {
                "entity_type": "Shot",
                "filters": [["id", "is", 1]],
                "fields": ["code"],
                "order": [{"field_name": "code", "direction": "desc"}],
                "filter_operator": "any",
                "retired_only": True,
                "include_archived_projects": False,
                "additional_filter_presets": [{"preset_name": "NAVIGATION_FILTER"}],
            },
        )
    ]


def test_get_missing_prints_null(harness: Any) -> None:
    harness.use_script_env()
    result = harness.run("get", "Shot", "999999999")
    assert (result.code, result.stdout, result.stderr) == (0, "null\n", "")


def test_get_missing_with_must_exist_exits_4(harness: Any) -> None:
    harness.use_script_env()
    result = harness.run("get", "Shot", "999999999", "--must-exist")
    assert result.code == 4
    assert result.stdout == ""
    assert result.error == {
        "type": "not_found",
        "message": "Shot 999999999 not found",
        "details": {"type": "Shot", "id": 999999999},
    }


def test_get_existing_with_must_exist_prints_it(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["find_one"] = SHOT
    assert harness.run("get", "Shot", "1", "--must-exist").json == SHOT


def test_get_needs_an_integer_id(harness: Any) -> None:
    harness.use_script_env()
    result = harness.run("get", "Shot", "sh010")
    assert result.code == 2
    assert harness.client.calls == []
