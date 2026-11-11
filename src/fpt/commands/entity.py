"""Entity commands: find, get, create, update, delete, revive."""

from __future__ import annotations

from typing import Any

import click

from fpt.commands._options import (
    JSON_ARG,
    archived_option,
    confirm,
    dry_run_option,
    fields_option,
    filter_options,
    order_option,
    presets_option,
    query_kwargs,
    retired_option,
    run,
    split_list,
    yes_option,
)
from fpt.context import AppContext
from fpt.data import build_data
from fpt.errors import NotFoundError, UsageError


@click.command()
@click.argument("entity_type", metavar="TYPE")
@filter_options
@fields_option
@order_option
@click.option("--limit", type=int, help="Return at most N entities (default: every match).")
@click.option("--page", type=int, help="Return page N of --limit entities.")
@retired_option
@archived_option
@presets_option
@click.pass_obj
def find(
    app: AppContext, entity_type: str, limit: int | None, page: int | None, **options: Any
) -> None:
    """Find entities of TYPE.

    TYPE is an entity type, such as Shot or Asset. Filter with -f (repeatable and ANDed;
    --any ORs them), or pass the raw API filter structure with --filters. With no --limit
    every match comes back, and with no --fields the library's default fields. Prints a list
    of entities.

    \b
    Examples:
      fpt find Shot -f 'project is Project:70' --fields code,sg_status_list
      fpt find Shot -f 'sg_status_list in ["ip","rev"]' --order -created_at --limit 10
      fpt find Version --filters '[["code", "contains", "v001"]]' --limit 50 --page 2
    """
    kwargs = {"entity_type": entity_type, **query_kwargs(**options)}
    if limit is not None:
        kwargs["limit"] = limit
    if page is not None:
        kwargs["page"] = page
    app.emit(app.client.find(**kwargs))


@click.command()
@click.argument("entity_type", metavar="TYPE")
@click.argument("entity_id", metavar="ID", type=int)
@fields_option
@order_option
@click.option("--any", "any_", is_flag=True, help="Send filter_operator 'any'.")
@retired_option
@archived_option
@presets_option
@click.option("--must-exist", is_flag=True, help="Exit 4 if there is no such entity.")
@click.pass_obj
def get(
    app: AppContext, entity_type: str, entity_id: int, must_exist: bool, **options: Any
) -> None:
    """Get one entity of TYPE by ID.

    TYPE is an entity type and ID the entity's id. Prints the entity, or null with exit 0
    when there is none, exactly as the library's find_one returns it. With --must-exist a
    missing entity exits 4 instead.

    \b
    Examples:
      fpt get Shot 1234 --fields code,sg_status_list
      fpt get Shot 1234 --must-exist
    """
    kwargs = {
        "entity_type": entity_type,
        **query_kwargs(filter_items=(), raw_filters=None, **options),
        "filters": [["id", "is", entity_id]],
    }
    result = app.client.find_one(**kwargs)
    if result is None and must_exist:
        raise NotFoundError(
            f"{entity_type} {entity_id} not found", {"type": entity_type, "id": entity_id}
        )
    app.emit(result)


UPDATE_MODES = ("set", "add", "remove")

set_option = click.option(
    "--set",
    "sets",
    multiple=True,
    metavar="FIELD=TEXT|FIELD:=JSON",
    help="A field value; repeatable. '=' gives text, ':=' gives typed JSON.",
)
data_option = click.option("--data", "raw_data", metavar=JSON_ARG, help="All fields as an object.")


def _modes(items: tuple[str, ...]) -> dict[str, str]:
    modes: dict[str, str] = {}
    for item in items:
        field, sep, mode = item.partition("=")
        if not sep or not field or mode not in UPDATE_MODES:
            raise UsageError(
                f"--multi-entity-mode {item!r} needs FIELD=MODE, "
                f"with MODE one of {', '.join(UPDATE_MODES)}."
            )
        modes[field] = mode
    return modes


@click.command()
@click.argument("entity_type", metavar="TYPE")
@set_option
@data_option
@click.option("--return-fields", metavar="A,B", help="Fields to return besides those set.")
@dry_run_option
@click.pass_obj
def create(
    app: AppContext,
    entity_type: str,
    sets: tuple[str, ...],
    raw_data: str | None,
    return_fields: str | None,
    dry_run: bool,
) -> None:
    """Create an entity of TYPE.

    TYPE is an entity type. Give field values with --set (repeatable): FIELD=TEXT sets a
    string, and FIELD:=JSON sets a typed value such as a number, a list or an entity link.
    --data gives all the fields as one JSON object, and --set wins over --data. Prints the
    new entity.

    \b
    Examples:
      fpt create Shot --set code=sh010 --set 'project:={"type": "Project", "id": 70}'
      fpt create Asset --data '{"code":"chair","project":{"type":"Project","id":70}}' --dry-run
    """
    kwargs: dict[str, Any] = {"entity_type": entity_type, "data": build_data(sets, raw_data)}
    if return_fields is not None:
        kwargs["return_fields"] = split_list(return_fields)
    run(app, "create", kwargs, dry_run=dry_run)


@click.command()
@click.argument("entity_type", metavar="TYPE")
@click.argument("entity_id", metavar="ID", type=int)
@set_option
@data_option
@click.option(
    "--multi-entity-mode",
    "modes",
    multiple=True,
    metavar="FIELD=set|add|remove",
    help="How a multi-entity field is changed; repeatable. The library default is set.",
)
@dry_run_option
@click.pass_obj
def update(
    app: AppContext,
    entity_type: str,
    entity_id: int,
    sets: tuple[str, ...],
    raw_data: str | None,
    modes: tuple[str, ...],
    dry_run: bool,
) -> None:
    """Update entity ID of TYPE.

    TYPE is an entity type and ID the entity's id. Field values work as for create: --set
    FIELD=TEXT, --set FIELD:=JSON, or --data. --multi-entity-mode chooses whether a
    multi-entity field's list is replaced (set), added to (add) or removed from (remove).
    Prints the updated fields.

    \b
    Examples:
      fpt update Shot 1234 --set sg_status_list=ip --set sg_cut_in:=1001
      fpt update Shot 1234 --set 'assets:=[{"type":"Asset","id":7}]' --multi-entity-mode assets=add
    """
    kwargs: dict[str, Any] = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "data": build_data(sets, raw_data),
    }
    if modes:
        kwargs["multi_entity_update_modes"] = _modes(modes)
    run(app, "update", kwargs, dry_run=dry_run)


@click.command()
@click.argument("entity_type", metavar="TYPE")
@click.argument("entity_id", metavar="ID", type=int)
@yes_option
@dry_run_option
@click.pass_obj
def delete(app: AppContext, entity_type: str, entity_id: int, yes: bool, dry_run: bool) -> None:
    """Retire (soft-delete) entity ID of TYPE.

    TYPE is an entity type and ID the entity's id. A retired entity can be brought back
    with revive. On a terminal, delete asks for confirmation; anywhere else it needs --yes.
    Prints true when the entity was retired.

    \b
    Examples:
      fpt delete Shot 1234 --yes
      fpt delete Shot 1234 --dry-run
    """
    if not (yes or dry_run):
        confirm("delete", f"Delete {entity_type} {entity_id}?")
    run(app, "delete", {"entity_type": entity_type, "entity_id": entity_id}, dry_run=dry_run)


@click.command()
@click.argument("entity_type", metavar="TYPE")
@click.argument("entity_id", metavar="ID", type=int)
@dry_run_option
@click.pass_obj
def revive(app: AppContext, entity_type: str, entity_id: int, dry_run: bool) -> None:
    """Revive a retired entity ID of TYPE.

    TYPE is an entity type and ID the id of an entity that delete retired. Prints true when
    the entity was revived.

    \b
    Examples:
      fpt revive Shot 1234
    """
    run(app, "revive", {"entity_type": entity_type, "entity_id": entity_id}, dry_run=dry_run)
