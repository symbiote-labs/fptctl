"""The wire format (spec, "Wire format"): Python values <-> JSON.

One definition, used for output, the call trace, and typed input.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from fptctl.errors import UsageError

AWARE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
NAIVE_FORMAT = "%Y-%m-%dT%H:%M:%S"
DATETIME_KEY = "$datetime"


def to_wire(value: Any) -> Any:
    """Return `value` as plain JSON data. Anything the spec does not list is a TypeError."""
    if value is None or isinstance(value, (str, int, float)):  # bool is an int
        return value
    if isinstance(value, dict):
        return {_key(key): to_wire(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_wire(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.strftime(NAIVE_FORMAT)
        return value.astimezone(timezone.utc).strftime(AWARE_FORMAT)
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Cannot represent a value of type {type(value).__name__} in JSON")


def _key(key: Any) -> str:
    if not isinstance(key, str):
        raise TypeError(f"Cannot represent a {type(key).__name__} dictionary key in JSON")
    return key


def dumps(value: Any, *, indent: int | None = None) -> str:
    return json.dumps(to_wire(value), indent=indent, ensure_ascii=False, allow_nan=False)


def _no_constant(name: str) -> Any:
    raise json.JSONDecodeError(f"{name} is not valid JSON", name, 0)


def loads(text: str) -> Any:
    """Parse strict JSON: Python's NaN, Infinity and -Infinity extensions are refused."""
    return json.loads(text, parse_constant=_no_constant)


def from_wire(value: Any) -> Any:
    """Decode typed input: {"$datetime": "..."} becomes a datetime. Nothing else is special."""
    if isinstance(value, dict):
        if list(value) == [DATETIME_KEY]:
            return parse_datetime(value[DATETIME_KEY])
        return {key: from_wire(item) for key, item in value.items()}
    if isinstance(value, list):
        return [from_wire(item) for item in value]
    return value


def parse_datetime(text: Any, what: str = f'"{DATETIME_KEY}"') -> datetime:
    """The wire format's datetime text: aware with a trailing Z, or naive."""
    if isinstance(text, str):
        try:
            if text.endswith("Z"):
                return datetime.strptime(text, AWARE_FORMAT).replace(tzinfo=timezone.utc)
            return datetime.strptime(text, NAIVE_FORMAT)
        except ValueError:
            pass
    raise UsageError(f'{what} needs "YYYY-MM-DDTHH:MM:SSZ" or "YYYY-MM-DDTHH:MM:SS", got {text!r}.')


def load_json_arg(raw: str, option: str, *, stdin: TextIO | None = None) -> Any:
    """Parse an option given as JSON, @FILE, or - (stdin), then decode typed input."""
    if raw == "-":
        text = (stdin or sys.stdin).read()
    elif raw.startswith("@"):
        try:
            text = Path(raw[1:]).read_text(encoding="utf-8")
        except OSError as exc:
            raise UsageError(f"{option}: cannot read {raw[1:]}: {exc.strerror}") from exc
    else:
        text = raw
    try:
        return from_wire(loads(text))
    except json.JSONDecodeError as exc:
        raise UsageError(f"{option} is not valid JSON: {exc}") from exc
