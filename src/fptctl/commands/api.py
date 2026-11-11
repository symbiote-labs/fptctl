"""API commands: methods and call, which reach any library method by name."""

from __future__ import annotations

import click

from fptctl.client import public_methods
from fptctl.context import AppContext
from fptctl.errors import UsageError
from fptctl.wire import load_json_arg


@click.group()
def api() -> None:
    """Call any library method by name."""


@api.command()
@click.pass_obj
def methods(app: AppContext) -> None:
    """List the library's public methods and their signatures.

    These are the methods `fptctl api call` can reach. They are read from the installed
    shotgun_api3 at run time, so a method a newer library adds is reachable with no fptctl
    change.

    \b
    Examples:
      fptctl api methods
      fptctl --format ndjson api methods
    """
    app.emit([{"name": name, "signature": sig} for name, sig in sorted(public_methods().items())])


@api.command()
@click.argument("method")
@click.option(
    "--args",
    "raw_args",
    default="{}",
    show_default=True,
    metavar="JSON|@FILE|-",
    help='Keyword arguments as a JSON object. {"$datetime": "..."} becomes a datetime.',
)
@click.pass_obj
def call(app: AppContext, method: str, raw_args: str) -> None:
    """Call METHOD with keyword arguments and print its return value.

    METHOD is any name from `fptctl api methods`. --args gives the keyword arguments as a JSON
    object, in which {"$datetime": "2026-11-10T14:30:00Z"} becomes a datetime. Use it for
    the methods with no command of their own, such as work_schedule_read.

    \b
    Examples:
      fptctl api call work_schedule_read --args @dates.json
      fptctl api call preferences_read --args '{"prefs": ["format_date_fields"]}'
    """
    if method not in public_methods():
        raise UsageError(f"Unknown method '{method}'. Run `fptctl api methods`.")
    arguments = load_json_arg(raw_args, "--args")
    if not isinstance(arguments, dict):
        raise UsageError("--args must be a JSON object of keyword arguments.")
    app.emit(getattr(app.client, method)(**arguments))
