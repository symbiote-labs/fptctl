from datetime import datetime, timezone
from typing import Any

import pytest
from parity.inventory import load_dimensions

from fptctl.errors import UsageError
from fptctl.filters import MULTI_ARG_OPERATORS, build_filters, parse_filter


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("code is 101", ["code", "is", 101]),
        ('code is "101"', ["code", "is", "101"]),
        ("code is sh010", ["code", "is", "sh010"]),
        ("flag is true", ["flag", "is", True]),
        ("flag is null", ["flag", "is", None]),
        ('sg_status_list in ["ip","rev"]', ["sg_status_list", "in", ["ip", "rev"]]),
        (
            'project is {"type":"Project","id":70}',
            ["project", "is", {"type": "Project", "id": 70}],
        ),
        ("project is Project:70", ["project", "is", {"type": "Project", "id": 70}]),
        ("entity is CustomEntity01:5", ["entity", "is", {"type": "CustomEntity01", "id": 5}]),
        ("entity is customentity01:5", ["entity", "is", "customentity01:5"]),
        ("entity is Project:7x", ["entity", "is", "Project:7x"]),
        ('created_at in_last [3,"DAY"]', ["created_at", "in_last", 3, "DAY"]),
        ("id between [1,5]", ["id", "between", 1, 5]),
        ("id not_between [1,5]", ["id", "not_between", 1, 5]),
        ("id in [1,5]", ["id", "in", [1, 5]]),
        ("id between 3", ["id", "between", 3]),
        ("code is a  b", ["code", "is", "a  b"]),
        ("  code   is   a b ", ["code", "is", "a b"]),
    ],
)
def test_parse_filter(text: str, expected: list[Any]) -> None:
    assert parse_filter(text) == expected


def test_a_datetime_value_decodes() -> None:
    assert parse_filter('created_at greater_than {"$datetime": "2026-11-10T14:30:00Z"}') == [
        "created_at",
        "greater_than",
        datetime(2026, 11, 10, 14, 30, tzinfo=timezone.utc),
    ]


@pytest.mark.parametrize("text", ["", "code", "code is", "code is   "])
def test_fewer_than_three_parts_is_a_usage_error(text: str) -> None:
    with pytest.raises(UsageError, match="FIELD OP VALUE"):
        parse_filter(text)


def test_build_filters_ands_shorthand_and_sets_any() -> None:
    assert build_filters(["code is a", "id is 1"], None, False) == (
        [["code", "is", "a"], ["id", "is", 1]],
        None,
    )
    assert build_filters(["code is a"], None, True) == ([["code", "is", "a"]], "any")
    assert build_filters([], None, False) == ([], None)


def test_build_filters_takes_the_raw_structure() -> None:
    raw = '{"filter_operator": "all", "filters": [["id", "is", 1]]}'
    assert build_filters([], raw, False) == (
        {"filter_operator": "all", "filters": [["id", "is", 1]]},
        None,
    )


@pytest.mark.parametrize(("shorthand", "any_"), [(["code is a"], False), ([], True)])
def test_raw_filters_cannot_be_mixed(shorthand: list[str], any_: bool) -> None:
    with pytest.raises(UsageError, match="--filters"):
        build_filters(shorthand, "[]", any_)


def test_multi_arg_operators_match_dimensions() -> None:
    assert list(MULTI_ARG_OPERATORS) == load_dimensions()["multi_arg_operators"]["operators"]


@pytest.mark.parametrize("word", ["NaN", "Infinity", "-Infinity"])
def test_non_standard_json_constants_stay_text(word: str) -> None:
    assert parse_filter(f"code is {word}") == ["code", "is", word]
