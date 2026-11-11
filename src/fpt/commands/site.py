"""Site-level commands."""

from __future__ import annotations

import click

from fpt.context import AppContext


@click.command()
@click.pass_obj
def info(app: AppContext) -> None:
    """Show server version and capabilities."""
    app.emit(app.client.info())
