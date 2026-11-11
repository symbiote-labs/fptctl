"""Root command group, global options, and the process-wide error boundary."""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

import click

from fpt import __version__
from fpt.client import translate_error
from fpt.commands.activity import activity, note, search
from fpt.commands.api import api
from fpt.commands.auth import auth
from fpt.commands.batch import batch
from fpt.commands.entity import create, delete, find, get, revive, update
from fpt.commands.files import attachment_group, download, thumbnail, upload
from fpt.commands.schema import schema
from fpt.commands.site import info
from fpt.commands.social import follow, followers, following, unfollow
from fpt.commands.summarize import summarize
from fpt.context import AppContext, Deps, default_deps
from fpt.errors import FptError, UsageError, emit_error
from fpt.output import FORMATS


def _enable_debug_logging() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    logging.getLogger("shotgun_api3").setLevel(logging.DEBUG)


@click.group(invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--profile", help="Named profile to use (see `fpt auth list`).")
@click.option("--site", help="Site URL; overrides the profile or FPT_SITE.")
@click.option("--format", "fmt", type=click.Choice(FORMATS), help="Output format.")
@click.option("--sudo-as", metavar="LOGIN", help="Act as this user (script auth only).")
@click.option("--no-color", is_flag=True, help="Disable coloured output.")
@click.option("--verbose", is_flag=True, help="Log API requests to stderr.")
@click.version_option(__version__, prog_name="fpt")
@click.pass_context
def cli(
    ctx: click.Context,
    profile: str | None,
    site: str | None,
    fmt: str | None,
    sudo_as: str | None,
    no_color: bool,
    verbose: bool,
) -> None:
    """Command-line interface for ShotGrid / Flow Production Tracking."""
    deps = ctx.obj if isinstance(ctx.obj, Deps) else default_deps()
    if verbose:
        _enable_debug_logging()
    ctx.obj = AppContext(
        deps=deps,
        profile=profile,
        site=site,
        fmt=fmt,
        sudo_as=sudo_as,
        color=not no_color and "NO_COLOR" not in deps.environ,
    )
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


cli.add_command(api)
cli.add_command(auth)
cli.add_command(info)
cli.add_command(find)
cli.add_command(get)
cli.add_command(create)
cli.add_command(update)
cli.add_command(delete)
cli.add_command(revive)
cli.add_command(batch)
cli.add_command(summarize)
cli.add_command(schema)
cli.add_command(upload)
cli.add_command(thumbnail)
cli.add_command(download)
cli.add_command(attachment_group)
cli.add_command(activity)
cli.add_command(note)
cli.add_command(search)
cli.add_command(follow)
cli.add_command(unfollow)
cli.add_command(followers)
cli.add_command(following)


def main(argv: Sequence[str] | None = None, *, deps: Deps | None = None) -> int:
    """Run fpt and return the process exit code. Every error is reported here."""
    args = list(argv) if argv is not None else None
    try:
        result = cli.main(args=args, prog_name="fpt", standalone_mode=False, obj=deps)
    except click.ClickException as exc:
        error: FptError = UsageError(exc.format_message())
    except click.Abort:
        error = UsageError("Aborted.")
    except Exception as exc:
        error = translate_error(exc)
    else:
        return result if isinstance(result, int) else 0
    emit_error(error, sys.stderr, is_tty=sys.stderr.isatty())
    return int(error.exit_code)
