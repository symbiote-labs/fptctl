import io
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from fpt.errors import UsageError
from fpt.output import format_cell, render, resolve_format

ROWS = [
    {
        "type": "Shot",
        "id": 1,
        "code": "sh010",
        "project": {"type": "Project", "id": 7, "name": "Demo"},
    },
    {"type": "Shot", "id": 2, "code": "sh020", "sg_status_list": None},
]


def rendered(data: Any, fmt: str) -> str:
    stream = io.StringIO()
    render(data, fmt, stream, color=False)
    return stream.getvalue()


def test_resolve_format_defaults_by_tty() -> None:
    assert resolve_format(None, is_tty=True) == "table"
    assert resolve_format(None, is_tty=False) == "json"


def test_resolve_format_explicit_wins() -> None:
    assert resolve_format("csv", is_tty=True) == "csv"


def test_resolve_format_rejects_unknown() -> None:
    with pytest.raises(UsageError):
        resolve_format("yaml", is_tty=False)


def test_json_round_trips_and_ends_with_newline() -> None:
    out = rendered(ROWS, "json")
    assert out.endswith("\n")
    assert json.loads(out) == ROWS


def test_json_serialises_aware_datetimes_as_utc_z() -> None:
    when = datetime(2026, 11, 10, 14, 30, tzinfo=timezone(timedelta(hours=5)))
    assert json.loads(rendered({"at": when}, "json")) == {"at": "2026-11-10T09:30:00Z"}


def test_json_serialises_naive_datetimes_without_offset() -> None:
    assert json.loads(rendered({"at": datetime(2026, 11, 10, 9, 30)}, "json")) == {
        "at": "2026-11-10T09:30:00"
    }


def test_json_refuses_values_it_cannot_represent() -> None:
    with pytest.raises(TypeError, match="object"):
        rendered({"x": object()}, "json")


def test_ndjson_is_one_object_per_line() -> None:
    lines = rendered(ROWS, "ndjson").splitlines()
    assert [json.loads(line) for line in lines] == ROWS


def test_ndjson_of_a_single_object_is_one_line() -> None:
    assert rendered({"a": 1}, "ndjson") == '{"a": 1}\n'


def test_csv_uses_union_of_columns_in_first_seen_order() -> None:
    lines = rendered(ROWS, "csv").splitlines()
    assert lines[0] == "type,id,code,project,sg_status_list"
    assert lines[1] == "Shot,1,sh010,Demo,"
    assert lines[2] == "Shot,2,sh020,,"


def test_csv_of_a_dict_is_key_value_rows() -> None:
    assert rendered({"version": [8, 2]}, "csv").splitlines() == ["key,value", 'version,"8, 2"']


def test_table_contains_headers_and_values() -> None:
    out = rendered(ROWS, "table")
    for expected in ("code", "sh010", "sh020", "Demo"):
        assert expected in out


def test_table_does_not_interpret_markup() -> None:
    assert "[bold]x[/bold]" in rendered([{"code": "[bold]x[/bold]"}], "table")


def test_table_of_empty_list_prints_nothing() -> None:
    assert rendered([], "table") == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (True, "true"),
        (5, "5"),
        ({"type": "Shot", "id": 3}, "Shot:3"),
        ({"type": "Shot", "id": 3, "name": "sh030"}, "sh030"),
        ([{"type": "Asset", "id": 1, "name": "a"}, {"type": "Asset", "id": 2}], "a, Asset:2"),
        (date(2026, 11, 10), "2026-11-10"),
        ({"x": 1}, '{"x": 1}'),
    ],
)
def test_format_cell(value: Any, expected: str) -> None:
    assert format_cell(value) == expected
