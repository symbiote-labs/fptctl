"""Click options shared by the entity commands, and the call-or-dry-run step."""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, TypeVar

import click

from fpt.client import describe_call
from fpt.context import AppContext
from fpt.errors import UsageError
from fpt.filters import build_filters, parse_value
from fpt.wire import dumps, load_json_arg, parse_datetime

F = TypeVar("F", bound=Callable[..., Any])
JSON_ARG = "JSON|@FILE|-"


def split_list(text: str) -> list[str]:
    """'a, b,c' -> ['a', 'b', 'c']. There is no quoting: a field name has no comma."""
    items = [item.strip() for item in text.split(",")]
    if not all(items):
        raise UsageError(f"{text!r} has an empty item; give names separated by commas.")
    return items


def parse_order(text: str) -> list[dict[str, str]]:
    """'code,-created_at' -> order clauses; a leading '-' sorts descending."""
    return [
        {"field_name": item[1:], "direction": "desc"}
        if item.startswith("-")
        else {"field_name": item, "direction": "asc"}
        for item in split_list(text)
    ]


def parse_entity(text: str, option: str) -> dict[str, Any]:
    """An entity link given as Type:123 or as a JSON object."""
    value = parse_value(text)
    if not isinstance(value, dict):
        raise UsageError(f"{option} needs an entity: Type:123 or a JSON object, got {text!r}.")
    return value


def parse_created_at(text: str) -> datetime:
    return parse_datetime(text, "--created-at")


def json_object(raw: str, option: str) -> dict[str, Any]:
    value = load_json_arg(raw, option)
    if not isinstance(value, dict):
        raise UsageError(f"{option} must be a JSON object.")
    return value


def stack(*decorators: Callable[[F], F]) -> Callable[[F], F]:
    def apply(func: F) -> F:
        for decorator in reversed(decorators):
            func = decorator(func)
        return func

    return apply


filter_options = stack(
    click.option(
        "-f",
        "--filter",
        "filter_items",
        multiple=True,
        metavar="'FIELD OP VALUE'",
        help="A condition; repeat to AND them. VALUE is JSON, Type:123, or text.",
    ),
    click.option("--any", "any_", is_flag=True, help="Match any condition instead of all."),
    click.option(
        "--filters", "raw_filters", metavar=JSON_ARG, help="The raw filter structure; not with -f."
    ),
)
fields_option = click.option("--fields", metavar="A,B", help="Fields to return.")
order_option = click.option("--order", metavar="A,-B", help="Sort fields; '-' for descending.")
retired_option = click.option(
    "--retired-only", is_flag=True, help="Return only retired (deleted) entities."
)
archived_option = click.option(
    "--include-archived-projects",
    "include_archived",
    type=click.BOOL,
    metavar="true|false",
    help="Include entities in archived projects (the library default is true).",
)
presets_option = click.option(
    "--additional-filter-presets", "raw_presets", metavar=JSON_ARG, help="Filter presets."
)
dry_run_option = click.option(
    "--dry-run", is_flag=True, help="Print the library call instead of making it."
)


def query_kwargs(
    *,
    filter_items: tuple[str, ...],
    any_: bool,
    raw_filters: str | None,
    fields: str | None = None,
    order: str | None = None,
    retired_only: bool = False,
    include_archived: bool | None = None,
    raw_presets: str | None = None,
) -> dict[str, Any]:
    """`filters` always, then only the options the user gave."""
    filters, operator = build_filters(filter_items, raw_filters, any_)
    kwargs: dict[str, Any] = {"filters": filters}
    if fields is not None:
        kwargs["fields"] = split_list(fields)
    if order is not None:
        kwargs["order"] = parse_order(order)
    if operator is not None:
        kwargs["filter_operator"] = operator
    if retired_only:
        kwargs["retired_only"] = True
    if include_archived is not None:
        kwargs["include_archived_projects"] = include_archived
    if raw_presets is not None:
        kwargs["additional_filter_presets"] = load_json_arg(
            raw_presets, "--additional-filter-presets"
        )
    return kwargs


def interactive() -> bool:
    return sys.stdin.isatty()


def confirm(command: str, question: str) -> None:
    """Ask on a TTY; off a TTY, refuse without --yes (spec, "Safety")."""
    if not interactive():
        raise UsageError(f"{command} needs --yes when stdin is not a terminal.")
    click.confirm(question, abort=True, err=True)


yes_option = click.option("--yes", is_flag=True, help="Do not ask for confirmation.")


def run(app: AppContext, method: str, kwargs: Mapping[str, Any], *, dry_run: bool = False) -> None:
    """Call `method` through the traced client and print its result, or with --dry-run, print the
    call it would make. A dry run resolves no credentials and builds no client."""
    if dry_run:
        sys.stdout.write(dumps(describe_call(method, kwargs), indent=2) + "\n")
        return
    app.emit(getattr(app.client, method)(**kwargs))
