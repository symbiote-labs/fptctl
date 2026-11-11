import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

CREATE = {"request_type": "create", "entity_type": "Shot", "data": {"code": "a"}}
DELETE = {"request_type": "delete", "entity_type": "Shot", "entity_id": 3}
SUMMARY = '[{"field": "id", "type": "record_count"}]'


def sent(harness: Any) -> list[tuple[str, dict[str, Any]]]:
    return [(name, kwargs) for name, _, kwargs in harness.client.calls]


@pytest.mark.parametrize(
    "text",
    [
        '[{"request_type": "create", "entity_type": "Shot", "data": {"code": "a"}},'
        ' {"request_type": "delete", "entity_type": "Shot", "entity_id": 3}]',
        '{"request_type": "create", "entity_type": "Shot", "data": {"code": "a"}}\n\n'
        '{"request_type": "delete", "entity_type": "Shot", "entity_id": 3}\n',
    ],
    ids=["array", "ndjson"],
)
def test_batch_reads_an_array_or_ndjson_from_stdin(harness: Any, text: str) -> None:
    harness.use_script_env()
    harness.client.responses["batch"] = [{"type": "Shot", "id": 9}, True]
    result = harness.run("batch", stdin=text)
    assert (result.code, result.json) == (0, [{"type": "Shot", "id": 9}, True])
    assert sent(harness) == [("batch", {"requests": [CREATE, DELETE]})]


def test_batch_reads_a_file_and_decodes_datetimes(harness: Any, tmp_path: Path) -> None:
    harness.use_script_env()
    path = tmp_path / "requests.ndjson"
    path.write_text(
        '{"request_type": "update", "entity_type": "Shot", "entity_id": 1,'
        ' "data": {"at": {"$datetime": "2026-11-10T14:30:00Z"}}}\n'
    )
    harness.run("batch", str(path))
    harness.run("batch", "-", stdin=f"[{path.read_text()}]")
    request = {
        "request_type": "update",
        "entity_type": "Shot",
        "entity_id": 1,
        "data": {"at": datetime(2026, 11, 10, 14, 30, tzinfo=timezone.utc)},
    }
    assert sent(harness) == [("batch", {"requests": [request]})] * 2


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"request_type": "create"}\n{nope\n', "line 2"),
        ("[1, 2]", "request objects"),
        ('"text"', "request objects"),
    ],
)
def test_batch_bad_input_is_a_usage_error(harness: Any, text: str, message: str) -> None:
    harness.use_script_env()
    result = harness.run("batch", stdin=text)
    assert result.code == 2
    assert message in result.error["message"]
    assert harness.client.calls == []


def test_batch_missing_file_is_a_usage_error(harness: Any, tmp_path: Path) -> None:
    harness.use_script_env()
    result = harness.run("batch", str(tmp_path / "missing.json"))
    assert result.code == 2
    assert "cannot read" in result.error["message"]


def test_batch_dry_run(harness: Any) -> None:
    result = harness.run("batch", "--dry-run", stdin=json.dumps([CREATE]))
    assert result.code == 0
    assert result.json == {"call": "batch", "args": {"requests": [CREATE]}}
    assert harness.built == []


def test_summarize_sends_filters_and_summary_fields(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["summarize"] = {"summaries": {"id": 2}, "groups": []}
    result = harness.run(
        "summarize", "Shot", "-f", "project is Project:70", "--summary-fields", SUMMARY
    )
    assert result.json == {"summaries": {"id": 2}, "groups": []}
    assert sent(harness) == [
        (
            "summarize",
            {
                "entity_type": "Shot",
                "filters": [["project", "is", {"type": "Project", "id": 70}]],
                "summary_fields": [{"field": "id", "type": "record_count"}],
            },
        )
    ]


def test_summarize_passes_each_option(harness: Any, tmp_path: Path) -> None:
    harness.use_script_env()
    grouping = tmp_path / "grouping.json"
    grouping.write_text('[{"field": "code", "type": "exact", "direction": "desc"}]')
    harness.run(
        "summarize", "Shot", "-f", "id is 1", "-f", "id is 2", "--any",
        "--summary-fields", SUMMARY, "--grouping", f"@{grouping}",
        "--include-archived-projects", "false",
    )  # fmt: skip
    assert sent(harness) == [
        (
            "summarize",
            {
                "entity_type": "Shot",
                "filters": [["id", "is", 1], ["id", "is", 2]],
                "filter_operator": "any",
                "summary_fields": [{"field": "id", "type": "record_count"}],
                "grouping": [{"field": "code", "type": "exact", "direction": "desc"}],
                "include_archived_projects": False,
            },
        )
    ]


def test_summarize_takes_raw_filters(harness: Any) -> None:
    harness.use_script_env()
    raw = '{"filter_operator": "all", "filters": [["id", "is", 1]]}'
    harness.run("summarize", "Shot", "--filters", raw, "--summary-fields", SUMMARY)
    assert sent(harness)[0][1]["filters"] == {
        "filter_operator": "all",
        "filters": [["id", "is", 1]],
    }


@pytest.mark.parametrize(
    "argv",
    [
        ["summarize", "Shot"],
        ["summarize", "Shot", "--summary-fields", "{nope"],
        ["summarize", "Shot", "--summary-fields", SUMMARY, "--grouping", "{nope"],
    ],
)
def test_summarize_usage_errors(harness: Any, argv: list[str]) -> None:
    harness.use_script_env()
    assert harness.run(*argv).code == 2
    assert harness.client.calls == []


def test_batch_rejects_nan(harness: Any) -> None:
    harness.use_script_env()
    result = harness.run("batch", stdin='{"request_type": "update", "data": {"x": NaN}}\n')
    assert result.code == 2
    assert harness.client.calls == []
