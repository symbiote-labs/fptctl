"""Follow commands: follow, unfollow, followers, following."""

from __future__ import annotations

from typing import Any

import click

from fpt.commands._options import dry_run_option, parse_entity, run
from fpt.context import AppContext


@click.command()
@click.argument("user", metavar="USER")
@click.argument("entity", metavar="ENTITY")
@dry_run_option
@click.pass_obj
def follow(app: AppContext, user: str, entity: str, dry_run: bool) -> None:
    """Make USER (HumanUser:123 or JSON) follow ENTITY (Type:123 or JSON)."""
    kwargs = {"user": parse_entity(user, "USER"), "entity": parse_entity(entity, "ENTITY")}
    run(app, "follow", kwargs, dry_run=dry_run)


@click.command()
@click.argument("user", metavar="USER")
@click.argument("entity", metavar="ENTITY")
@dry_run_option
@click.pass_obj
def unfollow(app: AppContext, user: str, entity: str, dry_run: bool) -> None:
    """Make USER (HumanUser:123 or JSON) stop following ENTITY (Type:123 or JSON)."""
    kwargs = {"user": parse_entity(user, "USER"), "entity": parse_entity(entity, "ENTITY")}
    run(app, "unfollow", kwargs, dry_run=dry_run)


@click.command()
@click.argument("entity", metavar="ENTITY")
@click.pass_obj
def followers(app: AppContext, entity: str) -> None:
    """The users who follow ENTITY (Type:123 or JSON)."""
    run(app, "followers", {"entity": parse_entity(entity, "ENTITY")})


@click.command()
@click.argument("user", metavar="USER")
@click.option("--project", metavar="Project:ID|JSON", help="Only entities in this project.")
@click.option("--entity-type", metavar="TYPE", help="Only entities of this type.")
@click.pass_obj
def following(app: AppContext, user: str, project: str | None, entity_type: str | None) -> None:
    """The entities USER (HumanUser:123 or JSON) follows."""
    kwargs: dict[str, Any] = {"user": parse_entity(user, "USER")}
    if project is not None:
        kwargs["project"] = parse_entity(project, "--project")
    if entity_type is not None:
        kwargs["entity_type"] = entity_type
    run(app, "following", kwargs)
