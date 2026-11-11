from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest


def sent(harness: Any) -> list[tuple[str, dict[str, Any]]]:
    return [(name, kwargs) for name, _, kwargs in harness.client.calls]


def test_activity(harness: Any, tmp_path: Path) -> None:
    harness.use_script_env()
    harness.client.responses["activity_stream_read"] = {"updates": [], "earliest_update_id": 1}
    result = harness.run("activity", "Shot", "12")
    assert (result.code, result.json) == (0, {"updates": [], "earliest_update_id": 1})
    path = tmp_path / "fields.json"
    path.write_text('{"Shot": ["code"]}')
    harness.run(
        "activity", "Shot", "12", "--entity-fields", f"@{path}", "--min-id", "3",
        "--max-id", "9", "--limit", "2",
    )  # fmt: skip
    base = {"entity_type": "Shot", "entity_id": 12}
    assert sent(harness) == [
        ("activity_stream_read", base),
        (
            "activity_stream_read",
            {**base, "entity_fields": {"Shot": ["code"]}, "min_id": 3, "max_id": 9, "limit": 2},
        ),
    ]


def test_note_thread(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["note_thread_read"] = [{"type": "Note", "id": 5}]
    result = harness.run("note", "thread", "5")
    assert (result.code, result.json) == (0, [{"type": "Note", "id": 5}])
    harness.run("note", "thread", "5", "--entity-fields", "-", stdin='{"Reply": ["content"]}')
    assert sent(harness) == [
        ("note_thread_read", {"note_id": 5}),
        ("note_thread_read", {"note_id": 5, "entity_fields": {"Reply": ["content"]}}),
    ]


def test_search(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["text_search"] = {"matches": [], "terms": ["x"]}
    result = harness.run("search", "x", "--entity-types", '{"Shot": []}')
    assert (result.code, result.json) == (0, {"matches": [], "terms": ["x"]})
    types = '{"Shot": [["created_at", "greater_than", {"$datetime": "2026-01-02T03:04:05Z"}]]}'
    harness.run(
        "search", "x", "--entity-types", types, "--project-id", "70", "--project-id", "71",
        "--limit", "5",
    )  # fmt: skip
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert sent(harness) == [
        ("text_search", {"text": "x", "entity_types": {"Shot": []}}),
        (
            "text_search",
            {
                "text": "x",
                "entity_types": {"Shot": [["created_at", "greater_than", when]]},
                "project_ids": [70, 71],
                "limit": 5,
            },
        ),
    ]


@pytest.mark.parametrize(
    "argv",
    [
        ["activity", "Shot", "x"],
        ["activity", "Shot", "1", "--entity-fields", "[1]"],
        ["activity", "Shot", "1", "--limit", "many"],
        ["note", "thread", "x"],
        ["note", "thread", "5", "--entity-fields", "{nope"],
        ["search", "x"],
        ["search", "x", "--entity-types", '["Shot"]'],
        ["search", "x", "--entity-types", '{"Shot": []}', "--project-id", "p"],
    ],
)
def test_activity_usage_errors(harness: Any, argv: list[str]) -> None:
    harness.use_script_env()
    assert harness.run(*argv).code == 2
    assert harness.client.calls == []
