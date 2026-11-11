"""Summarize command: aggregate values over the entities a filter matches."""

from __future__ import annotations

from typing import Any

import click

from fpt.commands._options import JSON_ARG, archived_option, filter_options, query_kwargs
from fpt.context import AppContext
from fpt.wire import load_json_arg


@click.command()
@click.argument("entity_type", metavar="TYPE")
@filter_options
@click.option(
    "--summary-fields",
    "raw_summary",
    required=True,
    metavar=JSON_ARG,
    help='[{"field": ..., "type": ...}, ...] as the library takes it.',
)
@click.option(
    "--grouping",
    "raw_grouping",
    metavar=JSON_ARG,
    help='[{"field": ..., "type": ..., "direction": ...}, ...] as the library takes it.',
)
@archived_option
@click.pass_obj
def summarize(
    app: AppContext,
    entity_type: str,
    raw_summary: str,
    raw_grouping: str | None,
    **options: Any,
) -> None:
    """Summarize fields of the TYPE entities that match the filters.

    TYPE is an entity type, filtered as with find. --summary-fields lists the aggregates as
    the library takes them, such as [{"field": "id", "type": "count"}], and --grouping groups
    them, such as [{"field": "sg_status_list", "type": "exact", "direction": "asc"}]. Prints
    the summaries, and the groups when there is a grouping.

    \b
    Examples:
      fpt summarize Shot -f 'project is Project:70' --summary-fields @count.json
      fpt summarize Task --summary-fields @sums.json --grouping @groups.json
    """
    kwargs: dict[str, Any] = {
        "entity_type": entity_type,
        **query_kwargs(**options),
        "summary_fields": load_json_arg(raw_summary, "--summary-fields"),
    }
    if raw_grouping is not None:
        kwargs["grouping"] = load_json_arg(raw_grouping, "--grouping")
    app.emit(app.client.summarize(**kwargs))
