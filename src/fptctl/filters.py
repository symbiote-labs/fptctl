"""Filter shorthand (spec, "Input shorthand") -> library filter lists."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from fptctl.errors import UsageError
from fptctl.wire import from_wire, load_json_arg, loads

# Must equal [multi_arg_operators] in parity/dimensions.toml (a unit test checks).
MULTI_ARG_OPERATORS = ("between", "not_between", "in_last", "not_in_last", "in_next", "not_in_next")
_LINK = re.compile(r"([A-Z][A-Za-z0-9_]*):(\d+)")


def parse_value(text: str) -> Any:
    """VALUE rules (spec, "Input shorthand"): JSON, then Type:123, then the text itself."""
    try:
        return from_wire(loads(text))
    except json.JSONDecodeError:
        pass
    link = _LINK.fullmatch(text)
    if link:
        return {"type": link.group(1), "id": int(link.group(2))}
    return text


def parse_filter(text: str) -> list[Any]:
    """'FIELD OP VALUE' -> [FIELD, OP, VALUE], spreading VALUE for multi-argument operators."""
    parts = text.strip().split(None, 2)
    if len(parts) < 3:
        raise UsageError(f"Filter {text!r} needs FIELD OP VALUE, e.g. -f 'code is sh010'.")
    field, operator, raw = parts
    value = parse_value(raw)
    if operator in MULTI_ARG_OPERATORS and isinstance(value, list):
        return [field, operator, *value]
    return [field, operator, value]


def build_filters(shorthand: Sequence[str], raw: str | None, any_: bool) -> tuple[Any, str | None]:
    """Return (filters, filter_operator) for the library call."""
    if raw is not None:
        if shorthand or any_:
            raise UsageError("--filters cannot be combined with -f or --any.")
        return load_json_arg(raw, "--filters"), None
    return [parse_filter(item) for item in shorthand], ("any" if any_ else None)
