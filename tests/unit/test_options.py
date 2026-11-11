from datetime import datetime, timezone

import pytest

from fptctl.commands._options import (
    json_object,
    parse_created_at,
    parse_entity,
    parse_order,
    query_kwargs,
    split_list,
)
from fptctl.errors import UsageError

PRESETS = (
    '[{"preset_name": "LATEST", "latest_by": "BY_PIPELINE_STEP_NUMBER_AND_ENTITIES_CREATED_AT"}]'
)


def test_split_list() -> None:
    assert split_list("code") == ["code"]
    assert split_list("code, sg_status_list,id") == ["code", "sg_status_list", "id"]
    for bad in ("", "a,,b", "a,"):
        with pytest.raises(UsageError, match="empty item"):
            split_list(bad)


def test_parse_order_always_sends_the_direction() -> None:
    assert parse_order("code,-created_at") == [
        {"field_name": "code", "direction": "asc"},
        {"field_name": "created_at", "direction": "desc"},
    ]


def test_query_kwargs_passes_only_what_was_given() -> None:
    assert query_kwargs(filter_items=(), any_=False, raw_filters=None) == {"filters": []}
    assert query_kwargs(
        filter_items=("id is 1",),
        any_=True,
        raw_filters=None,
        fields="code",
        order="-id",
        retired_only=True,
        include_archived=False,
        raw_presets=PRESETS,
    ) == {
        "filters": [["id", "is", 1]],
        "filter_operator": "any",
        "fields": ["code"],
        "order": [{"field_name": "id", "direction": "desc"}],
        "retired_only": True,
        "include_archived_projects": False,
        "additional_filter_presets": [
            {
                "preset_name": "LATEST",
                "latest_by": "BY_PIPELINE_STEP_NUMBER_AND_ENTITIES_CREATED_AT",
            }
        ],
    }
    assert query_kwargs(filter_items=(), any_=False, raw_filters=None, include_archived=True) == {
        "filters": [],
        "include_archived_projects": True,
    }


@pytest.mark.parametrize("text", ["Project:70", '{"type": "Project", "id": 70}'])
def test_parse_entity(text: str) -> None:
    assert parse_entity(text, "--project") == {"type": "Project", "id": 70}


@pytest.mark.parametrize("text", ["70", "x", "[1]", "project:70"])
def test_parse_entity_refuses_other_values(text: str) -> None:
    with pytest.raises(UsageError, match="--project"):
        parse_entity(text, "--project")


def test_parse_created_at() -> None:
    assert parse_created_at("2026-11-10T14:30:00Z") == datetime(
        2026, 11, 10, 14, 30, tzinfo=timezone.utc
    )
    assert parse_created_at("2026-11-10T14:30:00") == datetime(2026, 11, 10, 14, 30)
    with pytest.raises(UsageError, match="--created-at"):
        parse_created_at("yesterday")


def test_json_object() -> None:
    assert json_object('{"a": 1}', "--properties") == {"a": 1}
    with pytest.raises(UsageError, match="--properties must be a JSON object"):
        json_object("[1]", "--properties")
