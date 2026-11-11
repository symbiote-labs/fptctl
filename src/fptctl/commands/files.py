"""File commands: upload, thumbnail upload/share, download, attachment url."""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from fptctl.commands._options import (
    dry_run_option,
    parse_created_at,
    parse_entity,
    run,
    stack,
)
from fptctl.context import AppContext
from fptctl.errors import UsageError
from fptctl.wire import from_wire, loads

upload_options = stack(
    click.option("--display-name", help="The Attachment's display name."),
    click.option("--tag-list", help="Tags for the Attachment, comma-separated."),
    click.option(
        "--created-at", metavar="YYYY-MM-DDTHH:MM:SSZ", help="The upload's creation time."
    ),
)


def _upload_kwargs(
    display_name: str | None, tag_list: str | None, created_at: str | None
) -> dict[str, Any]:
    """Only the options the user gave."""
    kwargs: dict[str, Any] = {}
    if display_name is not None:
        kwargs["display_name"] = display_name
    if tag_list is not None:
        kwargs["tag_list"] = tag_list
    if created_at is not None:
        kwargs["created_at"] = parse_created_at(created_at)
    return kwargs


def _attachment(text: str) -> Any:
    """ATTACHMENT is JSON: an Attachment id, or the value of a file/link field."""
    try:
        value = from_wire(loads(text))
    except json.JSONDecodeError as exc:
        raise UsageError(f"ATTACHMENT is not valid JSON: {exc}") from exc
    if isinstance(value, bool) or not isinstance(value, (int, dict)):
        raise UsageError(f"ATTACHMENT needs an id or a JSON object, got {text!r}.")
    return value


@click.command()
@click.argument("entity_type", metavar="TYPE")
@click.argument("entity_id", metavar="ID", type=int)
@click.argument("path", metavar="PATH")
@click.option("--field-name", help="The file/link field to hold the upload.")
@upload_options
@dry_run_option
@click.pass_obj
def upload(
    app: AppContext,
    entity_type: str,
    entity_id: int,
    path: str,
    field_name: str | None,
    dry_run: bool,
    **options: Any,
) -> None:
    """Upload the file at PATH to entity ID of TYPE.

    TYPE is an entity type, ID the entity's id and PATH a local file. With --field-name the
    file goes into that file/link field; without it, it is attached to the entity. Prints
    the new Attachment's id.

    \b
    Examples:
      fptctl upload Shot 1234 plate.mov --field-name sg_uploaded_movie
      fptctl upload Shot 1234 notes.pdf --display-name "Client notes" --tag-list review
    """
    kwargs: dict[str, Any] = {"entity_type": entity_type, "entity_id": entity_id, "path": path}
    if field_name is not None:
        kwargs["field_name"] = field_name
    run(app, "upload", {**kwargs, **_upload_kwargs(**options)}, dry_run=dry_run)


@click.group()
def thumbnail() -> None:
    """Upload and share thumbnails."""


@thumbnail.command("upload")
@click.argument("entity_type", metavar="TYPE")
@click.argument("entity_id", metavar="ID", type=int)
@click.argument("path", metavar="PATH")
@click.option("--filmstrip", is_flag=True, help="Upload a filmstrip thumbnail.")
@upload_options
@dry_run_option
@click.pass_obj
def thumbnail_upload(
    app: AppContext,
    entity_type: str,
    entity_id: int,
    path: str,
    filmstrip: bool,
    dry_run: bool,
    **options: Any,
) -> None:
    """Set the thumbnail of entity ID of TYPE from the image at PATH.

    TYPE is an entity type, ID the entity's id and PATH a local image. With --filmstrip the
    image is a filmstrip, frames side by side, for scrubbing in the web UI. Prints the
    Attachment id the library returns.

    \b
    Examples:
      fptctl thumbnail upload Shot 1234 thumb.png
      fptctl thumbnail upload Shot 1234 strip.png --filmstrip
    """
    method = "upload_filmstrip_thumbnail" if filmstrip else "upload_thumbnail"
    kwargs = {"entity_type": entity_type, "entity_id": entity_id, "path": path}
    run(app, method, {**kwargs, **_upload_kwargs(**options)}, dry_run=dry_run)


@thumbnail.command("share")
@click.argument("entities", metavar="ENTITY...", nargs=-1, required=True)
@click.option("--path", "thumbnail_path", metavar="FILE", help="Upload this image and share it.")
@click.option("--source", metavar="ENTITY", help="Share this entity's thumbnail.")
@click.option("--filmstrip", is_flag=True, help="Share a filmstrip thumbnail.")
@upload_options
@dry_run_option
@click.pass_obj
def thumbnail_share(
    app: AppContext,
    entities: tuple[str, ...],
    thumbnail_path: str | None,
    source: str | None,
    filmstrip: bool,
    dry_run: bool,
    **options: Any,
) -> None:
    """Give every ENTITY the same thumbnail.

    Each ENTITY is Type:123 or a JSON object. Give the image with --path, which uploads it
    once and shares it with the rest, or with --source, which shares the thumbnail another
    entity already has. A thumbnail the server is still processing cannot be shared yet
    (exit 5). Prints the Attachment id.

    \b
    Examples:
      fptctl thumbnail share Shot:1234 Shot:1235 --path thumb.png
      fptctl thumbnail share Task:55 Task:56 --source Shot:1234
    """
    if (thumbnail_path is None) == (source is None):
        raise UsageError("Give exactly one of --path and --source.")
    kwargs: dict[str, Any] = {"entities": [parse_entity(item, "ENTITY") for item in entities]}
    if thumbnail_path is not None:
        kwargs["thumbnail_path"] = thumbnail_path
    if source is not None:
        kwargs["source_entity"] = parse_entity(source, "--source")
    if filmstrip:
        kwargs["filmstrip_thumbnail"] = True
    run(app, "share_thumbnail", {**kwargs, **_upload_kwargs(**options)}, dry_run=dry_run)


@click.command()
@click.argument("attachment", metavar="ATTACHMENT")
@click.option(
    "-o",
    "--output",
    required=True,
    metavar="PATH|-",
    help="Write the file to PATH and print PATH, or write the raw bytes to stdout with '-'.",
)
@click.pass_obj
def download(app: AppContext, attachment: str, output: str) -> None:
    """Download ATTACHMENT to a file or to stdout.

    ATTACHMENT is an Attachment id, or the value of a file/link field as JSON, as find
    returns it. With -o PATH the file is written there and PATH is printed; with -o - the
    raw bytes go to stdout, for piping.

    \b
    Examples:
      fptctl download 941 -o plate.mov
      fptctl download '{"type": "Attachment", "id": 941}' -o - | shasum
    """
    if not output:
        raise UsageError("-o needs a PATH, or '-' for stdout.")
    value = _attachment(attachment)
    if output != "-":
        run(app, "download_attachment", {"attachment": value, "file_path": output})
        return
    data = app.client.download_attachment(attachment=value)
    if isinstance(data, bytes):
        sys.stdout.flush()
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    else:
        app.emit(data)


@click.group("attachment")
def attachment_group() -> None:
    """Attachment helpers."""


@attachment_group.command("url")
@click.argument("attachment", metavar="ATTACHMENT")
@click.pass_obj
def attachment_url(app: AppContext, attachment: str) -> None:
    """Print the download URL of ATTACHMENT.

    ATTACHMENT is an Attachment id, or the value of a file/link field as JSON. The library
    builds the URL without a request; opening it in a browser needs a signed-in session.

    \b
    Examples:
      fptctl attachment url 941
    """
    run(app, "get_attachment_download_url", {"attachment": _attachment(attachment)})
