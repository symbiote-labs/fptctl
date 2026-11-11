"""Site commands: info."""

from __future__ import annotations

import click

from fptctl.context import AppContext


@click.command()
@click.pass_obj
def info(app: AppContext) -> None:
    """Show the server's version and capabilities.

    Prints what the library's info returns: the server version and the features it
    supports. It reads no entity data, so it is a quick check that a site answers.

    \b
    Examples:
      fptctl info
      fptctl --site https://studio.shotgrid.autodesk.com info
    """
    app.emit(app.client.info())
