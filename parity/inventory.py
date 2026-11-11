"""Burndown items (spec, "What an item is") and the items a case's trace covers."""

from __future__ import annotations

import inspect
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from parity.compare import wire

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

DIMENSIONS_PATH = Path(__file__).with_name("dimensions.toml")
CONSTRUCTOR = "Shotgun"
_WRITE_METHODS = ("create", "update")
_FILTER_METHODS = ("find", "find_one", "summarize")
_VARIADIC = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)


def load_dimensions(path: Path = DIMENSIONS_PATH) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def public_methods(cls: type) -> dict[str, inspect.Signature]:
    return {
        name: inspect.signature(member)
        for name, member in inspect.getmembers(cls, callable)
        if not name.startswith("_")
    }


def _parameters(signature: inspect.Signature) -> dict[str, inspect.Parameter]:
    """Every parameter except self, *args and **kwargs included (Decision 3)."""
    return {name: p for name, p in signature.parameters.items() if name != "self"}


def _passed(parameter: inspect.Parameter, args: Mapping[str, Any], named: set[str]) -> bool:
    """Whether the traced call gave this parameter a non-default value."""
    if parameter.kind is inspect.Parameter.VAR_KEYWORD:
        return any(key not in named for key in args)  # the trace merges **kwargs into args
    if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
        return bool(args.get(parameter.name))
    return parameter.name in args and _non_default(parameter, args[parameter.name])


def compute_items(
    cls: type, data_types: Mapping[str, bool], dimensions: Mapping[str, Any]
) -> list[str]:
    items: set[str] = set()
    for name, signature in public_methods(cls).items():
        items.add(f"method:{name}")
        items.update(f"param:{name}.{p}" for p in _parameters(signature))
    items.update(f"param:{CONSTRUCTOR}.{p}" for p in _parameters(inspect.signature(cls)))
    operators = dimensions["filter_operators"]
    for data_type, editable in data_types.items():
        items.add(f"field-read:{data_type}")
        if editable:
            items.add(f"field-write:{data_type}")
        items.update(f"filter-op:{data_type}.{op}" for op in operators.get(data_type, []))
    for enum, values in dimensions["enums"].items():
        items.update(f"enum-value:{enum}.{value}" for value in values)
    return sorted(items)


def _non_default(parameter: inspect.Parameter, value: Any) -> bool:
    if parameter.default is inspect.Parameter.empty:
        return True
    return bool(value != wire(parameter.default))


def _walk(value: Any, path: str) -> list[Any]:
    values = [value]
    for part in path.split("."):
        many = part.endswith("[]")
        key = part[:-2] if many else part
        found: list[Any] = []
        for current in values:
            if isinstance(current, dict) and key in current:
                item = current[key]
                found.extend(item if many and isinstance(item, list) else [] if many else [item])
        values = found
    return values


def _conditions(filters: Any) -> Iterator[tuple[str, str]]:
    if isinstance(filters, dict):
        yield from _conditions(filters.get("filters", []))
    elif isinstance(filters, list):
        for item in filters:
            if isinstance(item, dict):
                yield from _conditions(item.get("filters", []))
            elif (
                isinstance(item, list)
                and len(item) >= 2
                and all(isinstance(x, str) for x in item[:2])
            ):
                yield item[0], item[1]


def _entities(result: Any) -> list[dict[str, Any]]:
    rows = result if isinstance(result, list) else [result]
    return [row for row in rows if isinstance(row, dict) and isinstance(row.get("type"), str)]


def covered_items(
    *,
    argv: Sequence[str],
    trace: Sequence[Mapping[str, Any]],
    direct: Any,
    mode: str,
    schema_fields: Mapping[str, Mapping[str, str]],
    dimensions: Mapping[str, Any],
    cls: type,
) -> set[str]:
    covered: set[str] = set()
    constructor = _parameters(inspect.signature(cls))
    for line in trace:
        for name, value in line.get("construct", {}).items():
            if (
                name in constructor
                and constructor[name].kind not in _VARIADIC
                and _non_default(constructor[name], value)
            ):
                covered.add(f"param:{CONSTRUCTOR}.{name}")
    calls = [line for line in trace if "call" in line]
    if len(calls) != 1:
        return covered
    method, args = calls[0]["call"], calls[0]["args"]
    signatures = public_methods(cls)
    if method not in signatures:
        return covered
    surface = dimensions["surfaces"].get(method)
    via_api = list(argv[:3]) == ["api", "call", method]
    on_surface = list(argv[: len(surface.split())]) == surface.split() if surface else via_api
    if on_surface:
        covered.add(f"method:{method}")
    parameters = _parameters(signatures[method])
    named = {name for name, p in parameters.items() if p.kind not in _VARIADIC}
    for name, parameter in parameters.items():
        key = f"{method}.{name}"
        if _passed(parameter, args, named):
            if on_surface or (via_api and key in dimensions["not_exposed"]):
                covered.add(f"param:{key}")

    def data_type(entity_type: Any, field_name: Any) -> str | None:
        return schema_fields.get(str(entity_type), {}).get(str(field_name))

    if mode == "identical":
        for row in _entities(direct):
            for field_name, value in row.items():
                found = data_type(row["type"], field_name)
                if found and value is not None and value != []:
                    covered.add(f"field-read:{found}")
    writes = [(args.get("entity_type"), args.get("data"))] if method in _WRITE_METHODS else []
    if method == "batch":
        writes = [
            (request.get("entity_type"), request.get("data"))
            for request in args.get("requests") or []
            if isinstance(request, dict) and request.get("request_type") in _WRITE_METHODS
        ]
    for entity_type, data in writes:
        for field_name in data if isinstance(data, dict) else {}:
            found = data_type(entity_type, field_name)
            if found:
                covered.add(f"field-write:{found}")
    if "-f" in argv and method in _FILTER_METHODS:
        for field_name, operator in _conditions(args.get("filters")):
            found = data_type(args.get("entity_type"), field_name)
            if found and operator in dimensions["filter_operators"].get(found, []):
                covered.add(f"filter-op:{found}.{operator}")
    for location, enum in dimensions["enum_params"].items():
        location_method, _, path = location.partition(".")
        if location_method == method:
            for value in _walk(args, path):
                if value in dimensions["enums"].get(enum, []):
                    covered.add(f"enum-value:{enum}.{value}")
    return covered
