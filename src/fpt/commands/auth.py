"""Auth commands: sign in, and list, switch, check and remove profiles."""

from __future__ import annotations

import sys
from typing import Any

import click

from fpt.client import Credentials, normalize_site
from fpt.config import AUTH_TYPES, Profile, save_config
from fpt.context import AppContext
from fpt.errors import UsageError

_SECRET_LABELS = {"script": "API key", "user": "Password", "session": "Session token"}


def _verify(client: Any) -> None:
    """Make one authenticated request. `info()` would not do: it needs no login."""
    client.find_one("Project", [], ["id"])


def _read_secret(label: str, interactive: bool) -> str:
    if interactive:
        secret = str(click.prompt(label, hide_input=True, err=True))
    else:
        secret = sys.stdin.readline().strip()
    if not secret:
        raise UsageError(
            f"{label} is required. Pipe it on stdin, for example: "
            '`printf %s "$FPT_API_KEY" | fpt auth login --site ... --script-name ...`.'
        )
    return secret


def _choose_auth(
    script_name: str | None, login_name: str | None, use_session: bool, interactive: bool
) -> tuple[str, str | None, str | None]:
    """Return (auth type, script name, login), prompting only when interactive."""
    chosen = sum((script_name is not None, login_name is not None, use_session))
    if chosen > 1:
        raise UsageError("Choose only one of --script-name, --login, or --session.")
    if chosen == 1:
        kind = (
            "script" if script_name is not None else "user" if login_name is not None else "session"
        )
        return kind, script_name, login_name
    if not interactive:
        raise UsageError("One of --script-name, --login, or --session is required.")
    kind = click.prompt("Auth type", type=click.Choice(AUTH_TYPES), default="script", err=True)
    if kind == "script":
        return kind, str(click.prompt("Script name", err=True)), None
    if kind == "user":
        return kind, None, str(click.prompt("Login", err=True))
    return kind, None, None


@click.group()
def auth() -> None:
    """Manage sites and credentials."""


@auth.command()
@click.option("--name", default="default", show_default=True, help="Profile name.")
@click.option("--site", help="Site URL, e.g. https://studio.shotgrid.autodesk.com.")
@click.option("--script-name", help="Authenticate as this API script.")
@click.option("--login", "login_name", help="Authenticate as this user.")
@click.option("--session", "use_session", is_flag=True, help="Authenticate with a session token.")
@click.option("--http-proxy", help="Proxy as [user:pass@]host[:port].")
@click.option("--ca-certs", help="Path to a CA certificate bundle.")
@click.option("--otp", help="One-time 2FA code (with --login). Stores a session, not the password.")
@click.option("--no-verify", is_flag=True, help="Store the profile without contacting the site.")
@click.pass_obj
def login(
    app: AppContext,
    name: str,
    site: str | None,
    script_name: str | None,
    login_name: str | None,
    use_session: bool,
    http_proxy: str | None,
    ca_certs: str | None,
    otp: str | None,
    no_verify: bool,
) -> None:
    """Store credentials for a site as a named profile.

    Sign in one way: --script-name (an API script and its key), --login (a user and their
    password) or --session (a session token). The secret is read from a prompt on a
    terminal, or from stdin otherwise, and goes to the OS keychain; everything else goes to
    the config file. With --otp, the 2FA code is used once and only the session it opens is
    stored. The credentials are checked against the site unless --no-verify is given.

    \b
    Examples:
      fpt auth login --site https://studio.shotgrid.autodesk.com --script-name my_script
      fpt auth login --name me --site https://studio.shotgrid.autodesk.com --login jane --otp 123456
    """
    interactive = sys.stdin.isatty()
    if not site:
        if not interactive:
            raise UsageError("--site is required.")
        site = str(click.prompt("Site URL", err=True))
    kind, script, user = _choose_auth(script_name, login_name, use_session, interactive)
    secret = _read_secret(_SECRET_LABELS[kind], interactive)
    credentials = Credentials(
        site=normalize_site(site),
        auth=kind,
        secret=secret,
        script_name=script,
        login=user,
        http_proxy=http_proxy,
        ca_certs=ca_certs,
        auth_token=otp,
        source=f"profile:{name}",
    )
    if otp is not None:
        if kind != "user" or no_verify:
            raise UsageError("--otp needs --login and cannot be combined with --no-verify.")
        # A one-time code cannot be replayed, so keep the session it opens, not the password.
        client = app.deps.client_factory(credentials, sudo_as=None)
        _verify(client)
        kind, secret = "session", str(client.get_session_token())
    elif not no_verify:
        _verify(app.deps.client_factory(credentials, sudo_as=None))
    profile = Profile(
        name=name,
        site=credentials.site,
        auth=kind,
        script_name=script,
        login=user,
        http_proxy=http_proxy,
        ca_certs=ca_certs,
    )
    config = app.config.with_profile(profile)
    app.deps.secrets.set(name, secret)
    save_config(config, app.deps.config_path)
    app.emit(
        {"profile": name, "site": profile.site, "auth": kind, "default": config.default == name}
    )


@auth.command()
@click.argument("name", required=False)
@click.pass_obj
def logout(app: AppContext, name: str | None) -> None:
    """Remove a profile and its stored secret.

    NAME is the profile to remove; without NAME, the default profile. The secret is deleted
    from the keychain and the profile from the config file. Prints the removed profile and
    the new default.

    \b
    Examples:
      fpt auth logout me
      fpt auth logout
    """
    target = name or app.config.default
    if not target:
        raise UsageError("There is no profile to remove.")
    config = app.config.without_profile(target)
    app.deps.secrets.delete(target)
    save_config(config, app.deps.config_path)
    app.emit({"removed": target, "default": config.default})


@auth.command("list")
@click.pass_obj
def list_profiles(app: AppContext) -> None:
    """List the stored profiles.

    Each profile shows its site, how it signs in (script, user or session), who it signs in
    as, and whether it is the default. Secrets are never shown.

    \b
    Examples:
      fpt auth list
      fpt --format table auth list
    """
    config = app.config
    app.emit(
        [
            {
                "name": profile.name,
                "site": profile.site,
                "auth": profile.auth,
                "identity": profile.identity,
                "default": profile.name == config.default,
            }
            for _, profile in sorted(config.profiles.items())
        ]
    )


@auth.command()
@click.argument("name")
@click.pass_obj
def use(app: AppContext, name: str) -> None:
    """Make NAME the default profile.

    NAME is a profile from `fpt auth list`. Commands use the default profile unless
    --profile, the FPT_* credential variables or FPT_PROFILE choose another.

    \b
    Examples:
      fpt auth use me
    """
    config = app.config.with_default(name)
    save_config(config, app.deps.config_path)
    app.emit({"default": config.default})


@auth.command()
@click.pass_obj
def status(app: AppContext) -> None:
    """Check that the current credentials work.

    Makes one authenticated request with the credentials this command line resolves to:
    --profile, the FPT_* variables, FPT_PROFILE or the default profile, in that order.
    Prints the site, the auth type, the identity and where the credentials came from.

    \b
    Examples:
      fpt auth status
      fpt --profile me auth status
    """
    credentials = app.credentials
    _verify(app.client)
    app.emit(
        {
            "site": credentials.site,
            "auth": credentials.auth,
            "identity": credentials.identity,
            "source": credentials.source,
            "ok": True,
        }
    )


@auth.command()
@click.pass_obj
def token(app: AppContext) -> None:
    """Print a session token for the current credentials.

    The token can sign in later with FPT_SESSION_TOKEN or `auth login --session`, without a
    password. Each call opens a new session, so the token is different every time.

    \b
    Examples:
      fpt auth token
      fpt --profile me auth token
    """
    app.emit(app.client.get_session_token())
