"""Schema commands: entities, read, fields, field-create, field-update, field-delete."""

from __future__ import annotations

from typing import Any

import click

from fpt.commands._options import (
    JSON_ARG,
    confirm,
    dry_run_option,
    json_object,
    parse_entity,
    run,
    yes_option,
)
from fpt.context import AppContext

project_option = click.option(
    "--project", metavar="Project:ID|JSON", help="Read or change the schema as seen by a project."
)


def _project(kwargs: dict[str, Any], project: str | None) -> dict[str, Any]:
    if project is not None:
        kwargs["project_entity"] = parse_entity(project, "--project")
    return kwargs


@click.group()
def schema() -> None:
    """Read and change the site schema."""


@schema.command()
@project_option
@click.pass_obj
def entities(app: AppContext, project: str | None) -> None:
    """Every entity type and its properties."""
    run(app, "schema_entity_read", _project({}, project))


@schema.command()
@project_option
@click.pass_obj
def read(app: AppContext, project: str | None) -> None:
    """The whole schema: every field of every entity type."""
    run(app, "schema_read", _project({}, project))


@schema.command()
@click.argument("entity_type", metavar="TYPE")
@click.argument("field_name", metavar="[FIELD]", required=False)
@project_option
@click.pass_obj
def fields(app: AppContext, entity_type: str, field_name: str | None, project: str | None) -> None:
    """The fields of TYPE, or only FIELD."""
    kwargs: dict[str, Any] = {"entity_type": entity_type}
    if field_name is not None:
        kwargs["field_name"] = field_name
    run(app, "schema_field_read", _project(kwargs, project))


@schema.command("field-create")
@click.argument("entity_type", metavar="TYPE")
@click.argument("data_type", metavar="DATA_TYPE")
@click.argument("display_name", metavar="DISPLAY_NAME")
@click.option("--properties", "raw_properties", metavar=JSON_ARG, help="More field properties.")
@dry_run_option
@click.pass_obj
def field_create(
    app: AppContext,
    entity_type: str,
    data_type: str,
    display_name: str,
    raw_properties: str | None,
    dry_run: bool,
) -> None:
    """Create a field on TYPE; prints the new field's name."""
    kwargs: dict[str, Any] = {
        "entity_type": entity_type,
        "data_type": data_type,
        "display_name": display_name,
    }
    if raw_properties is not None:
        kwargs["properties"] = json_object(raw_properties, "--properties")
    run(app, "schema_field_create", kwargs, dry_run=dry_run)


@schema.command("field-update")
@click.argument("entity_type", metavar="TYPE")
@click.argument("field_name", metavar="FIELD")
@click.option(
    "--properties", "raw_properties", metavar=JSON_ARG, required=True, help="Properties to set."
)
@project_option
@dry_run_option
@click.pass_obj
def field_update(
    app: AppContext,
    entity_type: str,
    field_name: str,
    raw_properties: str,
    project: str | None,
    dry_run: bool,
) -> None:
    """Change the properties of FIELD on TYPE."""
    kwargs: dict[str, Any] = {
        "entity_type": entity_type,
        "field_name": field_name,
        "properties": json_object(raw_properties, "--properties"),
    }
    run(app, "schema_field_update", _project(kwargs, project), dry_run=dry_run)


@schema.command("field-delete")
@click.argument("entity_type", metavar="TYPE")
@click.argument("field_name", metavar="FIELD")
@yes_option
@dry_run_option
@click.pass_obj
def field_delete(
    app: AppContext, entity_type: str, field_name: str, yes: bool, dry_run: bool
) -> None:
    """Delete FIELD from TYPE."""
    if not (yes or dry_run):
        confirm("schema field-delete", f"Delete field {entity_type}.{field_name}?")
    kwargs = {"entity_type": entity_type, "field_name": field_name}
    run(app, "schema_field_delete", kwargs, dry_run=dry_run)
