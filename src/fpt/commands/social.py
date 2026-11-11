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
    """Make USER follow ENTITY.

    USER is a HumanUser (HumanUser:42 or JSON) and ENTITY any entity (Type:123 or JSON).
    Prints the result, which has "followed": true.

    \b
    Examples:
      fpt follow HumanUser:42 Shot:1234
      fpt follow HumanUser:42 Shot:1234 --dry-run
    """
    kwargs = {"user": parse_entity(user, "USER"), "entity": parse_entity(entity, "ENTITY")}
    run(app, "follow", kwargs, dry_run=dry_run)


@click.command()
@click.argument("user", metavar="USER")
@click.argument("entity", metavar="ENTITY")
@dry_run_option
@click.pass_obj
def unfollow(app: AppContext, user: str, entity: str, dry_run: bool) -> None:
    """Make USER stop following ENTITY.

    USER is a HumanUser (HumanUser:42 or JSON) and ENTITY any entity (Type:123 or JSON).
    Prints the result, which has "unfollowed": true.

    \b
    Examples:
      fpt unfollow HumanUser:42 Shot:1234
    """
    kwargs = {"user": parse_entity(user, "USER"), "entity": parse_entity(entity, "ENTITY")}
    run(app, "unfollow", kwargs, dry_run=dry_run)


@click.command()
@click.argument("entity", metavar="ENTITY")
@click.pass_obj
def followers(app: AppContext, entity: str) -> None:
    """List the users who follow ENTITY.

    ENTITY is any entity, as Type:123 or JSON. Prints a list of HumanUsers with their names
    and status.

    \b
    Examples:
      fpt followers Shot:1234
    """
    run(app, "followers", {"entity": parse_entity(entity, "ENTITY")})


@click.command()
@click.argument("user", metavar="USER")
@click.option("--project", metavar="Project:ID|JSON", help="Only entities in this project.")
@click.option("--entity-type", metavar="TYPE", help="Only entities of this type.")
@click.pass_obj
def following(app: AppContext, user: str, project: str | None, entity_type: str | None) -> None:
    """List the entities USER follows.

    USER is a HumanUser, as HumanUser:42 or JSON. Narrow the list with --project and
    --entity-type; without them it holds everything the user follows, which can be long.

    \b
    Examples:
      fpt following HumanUser:42 --project Project:70 --entity-type Shot
    """
    kwargs: dict[str, Any] = {"user": parse_entity(user, "USER")}
    if project is not None:
        kwargs["project"] = parse_entity(project, "--project")
    if entity_type is not None:
        kwargs["entity_type"] = entity_type
    run(app, "following", kwargs)
