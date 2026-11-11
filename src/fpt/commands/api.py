"""API commands: methods and call, which reach any library method by name."""

from __future__ import annotations

import click

from fpt.client import public_methods
from fpt.context import AppContext
from fpt.errors import UsageError
from fpt.wire import load_json_arg


@click.group()
def api() -> None:
    """Call any library method by name."""


@api.command()
@click.pass_obj
def methods(app: AppContext) -> None:
    """List the library's public methods and their signatures.

    These are the methods `fpt api call` can reach. They are read from the installed
    shotgun_api3 at run time, so a method a newer library adds is reachable with no fpt
    change.

    \b
    Examples:
      fpt api methods
      fpt --format ndjson api methods
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

    METHOD is any name from `fpt api methods`. --args gives the keyword arguments as a JSON
    object, in which {"$datetime": "2026-11-10T14:30:00Z"} becomes a datetime. Use it for
    the methods with no command of their own, such as work_schedule_read.

    \b
    Examples:
      fpt api call work_schedule_read --args '{"start_date":"2026-11-02","end_date":"2026-11-06"}'
      fpt api call preferences_read
    """
    if method not in public_methods():
        raise UsageError(f"Unknown method '{method}'. Run `fpt api methods`.")
    arguments = load_json_arg(raw_args, "--args")
    if not isinstance(arguments, dict):
        raise UsageError("--args must be a JSON object of keyword arguments.")
    app.emit(getattr(app.client, method)(**arguments))
