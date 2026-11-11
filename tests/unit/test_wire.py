import io
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from fptctl.errors import UsageError
from fptctl.wire import dumps, from_wire, load_json_arg, to_wire

PLUS_5 = timezone(timedelta(hours=5))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (True, True),
        (3, 3),
        (1.5, 1.5),
        ("x", "x"),
        ([1, (2, 3)], [1, [2, 3]]),
        ({"a": {"b": (1,)}}, {"a": {"b": [1]}}),
        (datetime(2026, 11, 10, 14, 30, tzinfo=PLUS_5), "2026-11-10T09:30:00Z"),
        (datetime(2026, 11, 10, 9, 30), "2026-11-10T09:30:00"),
        (date(2026, 11, 10), "2026-11-10"),
    ],
)
def test_to_wire(value: Any, expected: Any) -> None:
    assert to_wire(value) == expected


@pytest.mark.parametrize("value", [b"raw", object(), {1: "int key"}, {"x": {2.0}}])
def test_to_wire_refuses_what_the_spec_does_not_list(value: Any) -> None:
    with pytest.raises(TypeError):
        to_wire(value)


def test_dumps_refuses_nan() -> None:
    with pytest.raises(ValueError):
        dumps({"x": math.nan})


def test_dumps_keeps_non_ascii() -> None:
    assert dumps({"name": "café"}) == '{"name": "café"}'


def test_from_wire_decodes_aware_and_naive_datetimes() -> None:
    assert from_wire({"$datetime": "2026-11-10T14:30:00Z"}) == datetime(
        2026, 11, 10, 14, 30, tzinfo=timezone.utc
    )
    assert from_wire([{"$datetime": "2026-11-10T14:30:00"}]) == [datetime(2026, 11, 10, 14, 30)]


def test_from_wire_round_trips_output() -> None:
    value = {"at": datetime(2026, 11, 10, 9, 30, tzinfo=timezone.utc)}
    assert from_wire({"at": {"$datetime": to_wire(value)["at"]}}) == value


def test_only_a_lone_datetime_key_is_special() -> None:
    value = {"$datetime": "2026-11-10T14:30:00Z", "other": 1}
    assert from_wire(value) == value
    assert from_wire({"$date": "2026-11-10"}) == {"$date": "2026-11-10"}


@pytest.mark.parametrize("bad", ["2026-11-10", "2026-11-10T14:30:00+05:00", 5, None])
def test_bad_datetime_is_a_usage_error(bad: Any) -> None:
    with pytest.raises(UsageError, match=r"\$datetime"):
        from_wire({"$datetime": bad})


def test_load_json_arg_inline_file_and_stdin(tmp_path: Path) -> None:
    path = tmp_path / "args.json"
    path.write_text('{"a": {"$datetime": "2026-11-10T00:00:00Z"}}')
    expected = {"a": datetime(2026, 11, 10, tzinfo=timezone.utc)}
    assert load_json_arg('{"a": 1}', "--args") == {"a": 1}
    assert load_json_arg(f"@{path}", "--args") == expected
    assert load_json_arg("-", "--args", stdin=io.StringIO(path.read_text())) == expected


def test_load_json_arg_errors_name_the_option(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="--args is not valid JSON"):
        load_json_arg("{nope", "--args")
    with pytest.raises(UsageError, match="--args: cannot read"):
        load_json_arg(f"@{tmp_path / 'missing.json'}", "--args")


@pytest.mark.parametrize("text", ["NaN", "[1, Infinity]", '{"a": -Infinity}'])
def test_json_input_rejects_non_standard_constants(text: str) -> None:
    with pytest.raises(UsageError, match="not valid JSON"):
        load_json_arg(text, "--args")
