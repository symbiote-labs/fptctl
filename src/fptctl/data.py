"""--set / --data parsing (spec, "Input shorthand")."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from fptctl.errors import UsageError
from fptctl.wire import from_wire, load_json_arg, loads


def parse_set(item: str) -> tuple[str, Any]:
    """FIELD=VALUE gives a string; FIELD:=JSON gives a typed value."""
    key, sep, raw = item.partition("=")
    if not sep or not key or key == ":":
        raise UsageError(f"--set {item!r} needs FIELD=VALUE or FIELD:=JSON.")
    if key.endswith(":"):
        try:
            return key[:-1], from_wire(loads(raw))
        except json.JSONDecodeError as exc:
            raise UsageError(f"--set {item!r}: the value is not valid JSON: {exc}") from exc
    return key, raw


def build_data(sets: Sequence[str], raw: str | None) -> dict[str, Any]:
    """The data dict for create/update: --data first, then each --set on top."""
    data: dict[str, Any] = {}
    if raw is not None:
        loaded = load_json_arg(raw, "--data")
        if not isinstance(loaded, dict):
            raise UsageError("--data must be a JSON object.")
        data.update(loaded)
    for item in sets:
        key, value = parse_set(item)
        data[key] = value
    if not data:
        raise UsageError("Give the fields to set with --set or --data.")
    return data
