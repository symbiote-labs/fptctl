"""Batch command: several create, update and delete requests in one transaction."""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from fpt.commands._options import dry_run_option, run
from fpt.context import AppContext
from fpt.errors import UsageError
from fpt.wire import from_wire, loads


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        with open(path, encoding="utf-8") as stream:
            return stream.read()
    except OSError as exc:
        raise UsageError(f"batch: cannot read {path}: {exc.strerror}") from exc


def parse_requests(text: str) -> list[Any]:
    """A JSON array of requests, or NDJSON with one request per line."""
    try:
        loaded = loads(text)
    except json.JSONDecodeError:
        loaded = []
        for number, line in enumerate(text.splitlines(), start=1):
            if line.strip():
                try:
                    loaded.append(loads(line))
                except json.JSONDecodeError as exc:
                    raise UsageError(f"batch: line {number} is not valid JSON: {exc}") from exc
    if isinstance(loaded, dict):
        loaded = [loaded]
    if not isinstance(loaded, list) or not all(isinstance(item, dict) for item in loaded):
        raise UsageError("batch needs a JSON array of request objects, or one object per line.")
    requests: list[Any] = from_wire(loaded)
    return requests


@click.command()
@click.argument("path", metavar="[FILE]", default="-")
@dry_run_option
@click.pass_obj
def batch(app: AppContext, path: str, dry_run: bool) -> None:
    """Run create, update and delete requests from FILE in one transaction.

    FILE holds a JSON array of requests, or one request object per line (NDJSON). Without
    FILE, or with -, the requests are read from stdin. Each request is what the library's
    batch takes, such as {"request_type": "create", "entity_type": "Shot", "data": {...}}.
    Either every request succeeds or none does. Prints the list of results.

    \b
    Examples:
      fpt batch requests.ndjson
      fpt batch --dry-run - < requests.json
    """
    run(app, "batch", {"requests": parse_requests(_read(path))}, dry_run=dry_run)
