"""Activity commands: activity, note thread, search."""

from __future__ import annotations

from typing import Any

import click

from fpt.commands._options import JSON_ARG, json_object, run
from fpt.context import AppContext

entity_fields_option = click.option(
    "--entity-fields",
    "raw_entity_fields",
    metavar=JSON_ARG,
    help='Extra fields per entity type, e.g. {"Shot": ["code"]}.',
)


@click.command()
@click.argument("entity_type", metavar="TYPE")
@click.argument("entity_id", metavar="ID", type=int)
@entity_fields_option
@click.option("--min-id", type=int, help="Only updates with this id or higher.")
@click.option("--max-id", type=int, help="Only updates with this id or lower.")
@click.option("--limit", type=int, help="At most this many updates.")
@click.pass_obj
def activity(
    app: AppContext,
    entity_type: str,
    entity_id: int,
    raw_entity_fields: str | None,
    min_id: int | None,
    max_id: int | None,
    limit: int | None,
) -> None:
    """The activity stream of entity ID of TYPE."""
    kwargs: dict[str, Any] = {"entity_type": entity_type, "entity_id": entity_id}
    if raw_entity_fields is not None:
        kwargs["entity_fields"] = json_object(raw_entity_fields, "--entity-fields")
    if min_id is not None:
        kwargs["min_id"] = min_id
    if max_id is not None:
        kwargs["max_id"] = max_id
    if limit is not None:
        kwargs["limit"] = limit
    run(app, "activity_stream_read", kwargs)


@click.group()
def note() -> None:
    """Note helpers."""


@note.command()
@click.argument("note_id", metavar="NOTE_ID", type=int)
@entity_fields_option
@click.pass_obj
def thread(app: AppContext, note_id: int, raw_entity_fields: str | None) -> None:
    """The Note NOTE_ID with its Replies and Attachments."""
    kwargs: dict[str, Any] = {"note_id": note_id}
    if raw_entity_fields is not None:
        kwargs["entity_fields"] = json_object(raw_entity_fields, "--entity-fields")
    run(app, "note_thread_read", kwargs)


@click.command()
@click.argument("text", metavar="TEXT")
@click.option(
    "--entity-types",
    "raw_entity_types",
    metavar=JSON_ARG,
    required=True,
    help='Entity types to search, each with a filter list, e.g. {"Shot": []}.',
)
@click.option(
    "--project-id", "project_ids", type=int, multiple=True, help="Search this project; repeatable."
)
@click.option("--limit", type=int, help="At most this many matches.")
@click.pass_obj
def search(
    app: AppContext,
    text: str,
    raw_entity_types: str,
    project_ids: tuple[int, ...],
    limit: int | None,
) -> None:
    """Search entity names for TEXT."""
    kwargs: dict[str, Any] = {
        "text": text,
        "entity_types": json_object(raw_entity_types, "--entity-types"),
    }
    if project_ids:
        kwargs["project_ids"] = list(project_ids)
    if limit is not None:
        kwargs["limit"] = limit
    run(app, "text_search", kwargs)
