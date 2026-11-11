import functools
from datetime import date
from typing import Any

import pytest
import shotgun_api3
from parity.burndown import LATEST
from parity.inventory import covered_items, load_dimensions

from parity import fixtures, generate

DIMENSIONS = load_dimensions()
WAIVED = {"field-read:jsonb", "field-read:pivot_column", "field-write:entity_type",
          "field-write:password", "filter-op:number.not_between"}  # fmt: skip
PARITY_TYPES = ("checkbox", "date", "date_time", "duration", "entity", "float", "list",
                "multi_entity", "number", "percent", "status_list", "text", "url")  # fmt: skip
EDITABLE = {*PARITY_TYPES, "color", "entity_type", "image", "password", "serializable"}
SNAPSHOT: dict[str, Any] = {
    "data_types": {
        dt: dt in EDITABLE
        for dt in (
            *PARITY_TYPES,
            "calculated",
            "color",
            "entity_type",
            "image",
            "jsonb",
            "password",
            "pivot_column",
            "serializable",
            "summary",
            "uuid",
        )
    },  # fmt: skip
    "fields": {
        "Shot": {
            **{fixtures.field_name(dt): dt for dt in PARITY_TYPES},
            "id": "number",
            "code": "text",
            "project": "entity",
            "image": "image",
            "created_at": "date_time",
            "open_notes_count": "summary",
        },  # fmt: skip
        "Task": {
            "workload": "calculated",
            "color": "color",
            "splits": "serializable",
            "entity": "entity",
        },  # fmt: skip
        "Page": {"entity_type": "entity_type"},
        "HumanUser": {"password_proxy": "password"},
        "Icon": {"uuid": "uuid"},
    },
}
CONTEXT = {
    "project": {"type": "Project", "id": 70, "name": "fpt_parity_RUN"},
    "twin": {"type": "Shot", "id": 1, "name": "fpt_parity_twin"},
    "past": {"type": "Shot", "id": 2, "name": "fpt_parity_past"},
    "task": {"type": "Task", "id": 3, "name": "fpt_parity_task"},
    "dates": fixtures.run_dates(date(2026, 11, 10)),
}


def entries() -> list[tuple[str, dict[str, Any]]]:
    files = generate.generate(SNAPSHOT, DIMENSIONS, WAIVED, shotgun_api3.Shotgun)
    return [entry for found in files.values() for entry in found]


def unbound(method: str) -> Any:
    return functools.partial(getattr(shotgun_api3.Shotgun, method), None)


def test_every_generated_item_gets_a_case() -> None:
    items = {item for item, _ in entries()}
    assert len(items) == 21 + 16 + 95 + 36
    assert not items & WAIVED
    assert not items & generate.HAND_WRITTEN


@pytest.mark.parametrize(("item", "case"), entries(), ids=lambda value: str(value)[:60])
def test_each_case_covers_its_item(item: str, case: dict[str, Any]) -> None:
    direct = None
    if item.startswith("field-read:"):
        direct = [{"type": case["args"]["entity_type"], **dict.fromkeys(case["args"]["fields"], 1)}]
    covered = covered_items(
        argv=case["argv"],
        trace=[{"call": case["method"], "args": case["args"]}],
        direct=direct,
        mode=case["mode"],
        schema_fields=SNAPSHOT["fields"],
        dimensions=DIMENSIONS,
        cls=shotgun_api3.Shotgun,
    )
    assert item in covered


def test_text_leaves_object_and_number_placeholders_unquoted() -> None:
    value = {"a": "${project}", "b": ["${dates.day}", "${dates.future}"], "c": "${project.id}"}
    assert generate.text(value) == (
        '{"a": ${project}, "b": [${dates.day}, "${dates.future}"], "c": ${project.id}}'
    )


def test_a_type_without_a_recipe_is_reported() -> None:
    snapshot = {"data_types": {**SNAPSHOT["data_types"], "timecode": True}, "fields": {}}
    with pytest.raises(LookupError, match="field-read:timecode"):
        generate.generate(snapshot, DIMENSIONS, WAIVED, shotgun_api3.Shotgun)


@pytest.mark.skipif(not LATEST.exists(), reason="no schema snapshot; run parity.runner")
def test_the_committed_files_are_current() -> None:
    for name, found in generate.generate(*generate.load_inputs()).items():
        committed = (generate.CASES_DIR / name).read_text(encoding="utf-8")
        assert committed == generate.render(found), f"{name} is stale: run parity.generate"
