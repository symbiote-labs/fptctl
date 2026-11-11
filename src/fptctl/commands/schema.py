"""Schema commands: entities, read, fields, field-create, field-update, field-delete."""

from __future__ import annotations

from typing import Any

import click

from fptctl.commands._options import (
    JSON_ARG,
    confirm,
    dry_run_option,
    json_object,
    parse_entity,
    run,
    yes_option,
)
from fptctl.context import AppContext

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
    """List every entity type and its properties.

    Prints what the library's schema_entity_read returns: each entity type's display name,
    visibility and other properties. With --project, the schema as that project sees it.

    \b
    Examples:
      fptctl schema entities
      fptctl schema entities --project Project:70
    """
    run(app, "schema_entity_read", _project({}, project))


@schema.command()
@project_option
@click.pass_obj
def read(app: AppContext, project: str | None) -> None:
    """Read the whole schema: every field of every entity type.

    The result is large, so prefer `schema fields` for one entity type. With --project, the
    schema as that project sees it.

    \b
    Examples:
      fptctl schema read --project Project:70
    """
    run(app, "schema_read", _project({}, project))


@schema.command()
@click.argument("entity_type", metavar="TYPE")
@click.argument("field_name", metavar="[FIELD]", required=False)
@project_option
@click.pass_obj
def fields(app: AppContext, entity_type: str, field_name: str | None, project: str | None) -> None:
    """Read the fields of TYPE, or only FIELD.

    TYPE is an entity type and FIELD a field name such as sg_status_list. Each field comes
    with its data type, whether it is editable, its valid values and its other properties.
    With --project, the fields as that project sees them.

    \b
    Examples:
      fptctl schema fields Shot
      fptctl schema fields Shot sg_status_list --project Project:70
    """
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
    """Create a field on TYPE and print its name.

    TYPE is an entity type, DATA_TYPE a field data type such as text, number, list or
    entity, and DISPLAY_NAME the name people see. The server derives the field name
    (sg_...) from DISPLAY_NAME. --properties sets more, such as {"valid_types": ["Asset"]}
    for an entity field.

    \b
    Examples:
      fptctl schema field-create Shot text "Review notes"
      fptctl schema field-create Shot entity "Hero asset" --properties '{"valid_types": ["Asset"]}'
    """
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
    """Change the properties of FIELD on TYPE.

    TYPE is an entity type and FIELD the field name. --properties gives the properties to
    set as a JSON object, such as {"description": "..."}. With --project the change applies
    to that project only, for the properties that can differ per project, such as visible.

    \b
    Examples:
      fptctl schema field-update Shot sg_review_notes --properties '{"description": "From review"}'
      fptctl schema field-update Shot sg_review_notes --project Project:70 --properties @hide.json
    """
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
    """Delete FIELD from TYPE.

    TYPE is an entity type and FIELD the field name. The field goes to the site's Trash,
    and its name stays taken until someone deletes it there for good in the web UI. On a
    terminal, field-delete asks for confirmation; anywhere else it needs --yes.

    \b
    Examples:
      fptctl schema field-delete Shot sg_review_notes --yes
    """
    if not (yes or dry_run):
        confirm("schema field-delete", f"Delete field {entity_type}.{field_name}?")
    kwargs = {"entity_type": entity_type, "field_name": field_name}
    run(app, "schema_field_delete", kwargs, dry_run=dry_run)
