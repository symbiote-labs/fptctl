"""Render command results as json, ndjson, table, or csv."""

from __future__ import annotations

import csv
from datetime import date, datetime
from typing import Any, TextIO

from rich.console import Console
from rich.table import Table

from fpt.errors import UsageError
from fpt.wire import dumps, to_wire

FORMATS: tuple[str, ...] = ("json", "ndjson", "table", "csv")


def resolve_format(explicit: str | None, *, is_tty: bool) -> str:
    if explicit is None:
        return "table" if is_tty else "json"
    if explicit not in FORMATS:
        raise UsageError(f"Unknown format '{explicit}'. Choose one of: {', '.join(FORMATS)}.")
    return explicit


def _dumps(data: Any, indent: int | None = None) -> str:
    return dumps(data, indent=indent)


def format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime, date)):
        return str(to_wire(value))
    if isinstance(value, dict):
        if "type" in value and "id" in value:
            return str(value.get("name") or f"{value['type']}:{value['id']}")
        return _dumps(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(format_cell(item) for item in value)
    return str(value)


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        return [{"key": key, "value": value} for key, value in data.items()]
    if isinstance(data, list):
        return [row if isinstance(row, dict) else {"value": row} for row in data]
    return [{"value": data}]


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, None] = {}
    for row in rows:
        for key in row:
            seen.setdefault(key)
    return list(seen)


def _render_csv(data: Any, stream: TextIO) -> None:
    rows = _rows(data)
    columns = _columns(rows)
    if not columns:
        return
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([format_cell(row.get(column)) for column in columns])


def _render_table(data: Any, stream: TextIO, color: bool) -> None:
    rows = _rows(data)
    columns = _columns(rows)
    if not columns:
        return
    table = Table(*columns)
    for row in rows:
        table.add_row(*[format_cell(row.get(column)) for column in columns])
    Console(file=stream, no_color=not color, markup=False, highlight=False).print(table)


def render(data: Any, fmt: str, stream: TextIO, *, color: bool = True) -> None:
    if fmt == "json":
        stream.write(_dumps(data, indent=2) + "\n")
    elif fmt == "ndjson":
        for item in data if isinstance(data, list) else [data]:
            stream.write(_dumps(item) + "\n")
    elif fmt == "csv":
        _render_csv(data, stream)
    elif fmt == "table":
        _render_table(data, stream, color)
    else:
        raise UsageError(f"Unknown format '{fmt}'. Choose one of: {', '.join(FORMATS)}.")
