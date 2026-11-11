from datetime import datetime, timezone
from typing import Any

import pytest

from fptctl.data import build_data, parse_set
from fptctl.errors import UsageError


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ("code=sh010", ("code", "sh010")),
        ("code=101", ("code", "101")),
        ("code=", ("code", "")),
        ("code=a=b", ("code", "a=b")),
        ("sg_cut_in:=101", ("sg_cut_in", 101)),
        ('code:="101"', ("code", "101")),
        ('project:={"type":"Project","id":70}', ("project", {"type": "Project", "id": 70})),
        ("flag:=null", ("flag", None)),
        ("tags:=[1,2]", ("tags", [1, 2])),
    ],
)
def test_parse_set(item: str, expected: tuple[str, Any]) -> None:
    assert parse_set(item) == expected


def test_a_typed_datetime_decodes() -> None:
    assert parse_set('at:={"$datetime": "2026-11-10T14:30:00Z"}') == (
        "at",
        datetime(2026, 11, 10, 14, 30, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize("item", ["code", "=x", ":=1", "x:=", "x:={nope"])
def test_bad_set_is_a_usage_error(item: str) -> None:
    with pytest.raises(UsageError, match="--set"):
        parse_set(item)


def test_set_overrides_data() -> None:
    assert build_data(["code=b", "n:=2"], '{"code": "a", "x": 1}') == {
        "code": "b",
        "x": 1,
        "n": 2,
    }


def test_data_decodes_datetimes() -> None:
    assert build_data([], '{"at": {"$datetime": "2026-11-10T14:30:00"}}') == {
        "at": datetime(2026, 11, 10, 14, 30)
    }


@pytest.mark.parametrize("raw", ["[1]", "1", "null"])
def test_data_must_be_an_object(raw: str) -> None:
    with pytest.raises(UsageError, match="JSON object"):
        build_data([], raw)


@pytest.mark.parametrize(("sets", "raw"), [([], None), ([], "{}")])
def test_no_data_is_a_usage_error(sets: list[str], raw: str | None) -> None:
    with pytest.raises(UsageError, match="--set or --data"):
        build_data(sets, raw)


def test_typed_set_rejects_nan() -> None:
    with pytest.raises(UsageError, match="not valid JSON"):
        parse_set("x:=NaN")
