# fptctl

A command-line interface for ShotGrid / Flow Production Tracking. `fptctl` is a thin wrapper around the
official [`shotgun_api3`](https://github.com/shotgunsoftware/python-api) library: each command makes
one library call with the arguments you give it and prints what the library returns.

It is built for people, scripts and AI agents alike: JSON when piped, tables on a terminal, stable exit
codes, and no prompts when stdin is not a terminal.

`fptctl` is built on `shotgun_api3` 3.10.5 and pins that exact release, the one its parity suite verifies
against a live site (see Development).

## Install

`fptctl` needs Python 3.10 or newer.

```shell
uv tool install git+https://github.com/symbiote-labs/fptctl@v0.2.0
# or: pip install git+https://github.com/symbiote-labs/fptctl@v0.2.0
fptctl --version
```

From a checkout, `uv tool install .` (or `pip install .`).

fptctl was called `fpt` in 0.1.0. It was renamed in 0.2.0 so that it can sit next to
[`dcc-mcp/fpt-cli`](https://github.com/dcc-mcp/fpt-cli), a separate Rust ShotGrid CLI whose
command is also `fpt`. If you used 0.1.0: uninstall it (`uv tool uninstall fpt-cli`), rename your
`FPT_*` variables to `FPTCTL_*`, and run `fptctl auth login` again, since profiles now live in
`~/.config/fptctl/` and the keychain service `fptctl`. The PyPI package named `fpt-cli` is an
unrelated project.

## Agent skill

`skills/fptctl` is an agent skill that teaches an AI coding agent to install and use `fptctl`. Add it to
a project with:

```shell
npx skills add symbiote-labs/fptctl --skill fptctl
```

Its command reference is generated from the command docstrings, so it matches `fptctl --help`.

## Authentication

Store credentials once as a named profile. The site and the non-secret settings go to
`~/.config/fptctl/config.toml` (or `$XDG_CONFIG_HOME/fptctl/config.toml`, or the path in `FPTCTL_CONFIG`); the
secret goes to the OS keychain under the service `fptctl`.

```shell
fptctl auth login --site https://studio.shotgrid.autodesk.com --script-name my_script   # API script
fptctl auth login --name me --site https://studio.shotgrid.autodesk.com --login jane       # user login
# With 2FA: stores a session, not the password
fptctl auth login --name me --site https://studio.shotgrid.autodesk.com --login jane --otp 123456
fptctl auth list        # profiles
fptctl auth use me      # make "me" the default
fptctl auth status      # check the current credentials work
fptctl auth logout me
```

`auth login` reads the secret (API key, password, or session token with `--session`) from a prompt, or
from stdin when stdin is not a terminal. `--http-proxy` and `--ca-certs` are stored with the profile.

Credentials are taken from the first of:

1. `--profile NAME`;
2. environment variables: `FPTCTL_SITE` with `FPTCTL_SCRIPT_NAME` and `FPTCTL_API_KEY`, or with `FPTCTL_LOGIN`
   and `FPTCTL_PASSWORD`, or with `FPTCTL_SESSION_TOKEN`;
3. the profile named by `FPTCTL_PROFILE`;
4. the default profile.

`--site` overrides the site from any of these. With the environment variables, `FPTCTL_HTTP_PROXY` and
`FPTCTL_CA_CERTS` set the proxy and the CA bundle; a profile uses the ones stored with it.

On a machine with no keychain backend (a headless Linux server, for one) `auth login` fails with a
keychain error. Use the environment variables there instead.

## Output

Results go to stdout and everything else to stderr. The default format is `table` on a terminal and
`json` otherwise; choose one with `--format json|ndjson|table|csv`. JSON output is the library's
return value, with nothing added, removed or renamed.

Values are written as JSON, and timezone-aware datetimes as UTC text (`2026-11-10T14:30:00Z`). Wherever `fptctl` reads
JSON (`--data`, `--set field:=`, `--filters`, `api call --args` and the other JSON options), the
object `{"$datetime": "2026-11-10T14:30:00Z"}` becomes a datetime. Dates are plain `YYYY-MM-DD`
strings. Options shown as `JSON|@FILE|-` in `--help` also read a file (`@FILE`) or stdin (`-`).

Other global options: `--sudo-as LOGIN` (act as a user, with script credentials), `--verbose` (log
requests to stderr), `--no-color`.

## Commands

Run `fptctl COMMAND --help` for every option.

### Find and change entities

```shell
fptctl find Shot -f 'project is Project:70' -f 'sg_status_list in ["ip","rev"]' --fields code,sg_status_list
fptctl find Shot --filters @filters.json --order -created_at --limit 10
fptctl get Shot 1234 --fields code
fptctl get Shot 1234 --must-exist           # exit 4 instead of printing null
fptctl create Shot --set code=sh010 --set 'project:={"type":"Project","id":70}'
fptctl update Shot 1234 --set sg_cut_in:=1001 --data @more.json
fptctl delete Shot 1234 --yes
fptctl revive Shot 1234
fptctl batch requests.ndjson                # create/update/delete requests in one transaction
fptctl summarize Shot -f 'project is Project:70' --summary-fields '[{"field":"id","type":"count"}]'
```

**Filters.** `-f 'FIELD OP VALUE'` is repeatable and ANDed (`--any` ORs them). VALUE is JSON if it
parses as JSON (`5`, `true`, `null`, `"101"`, `["ip","rev"]`), an entity link if it looks like
`Type:123`, and text otherwise. So `code is 101` sends a number and `code is "101"` a string. For
`between`, `in_last`, `in_next` and their negations, a JSON array is spread into the operator's
arguments: `-f 'created_at in_last [3,"DAY"]'`. `--filters` takes the raw API structure instead and
cannot be mixed with `-f`.

**Data.** `--set field=value` sets text, `--set field:=JSON` sets a typed value, and `--data` gives a
whole object. `--set` wins over `--data`.

**Safety.** `delete` and `schema field-delete` ask for confirmation on a terminal and need `--yes`
otherwise. Every command that writes to the site takes `--dry-run`, which prints the library call it
would make and makes no request.

### Schema

```shell
fptctl schema entities
fptctl schema fields Shot sg_status_list --project Project:70
fptctl schema field-create Shot text "Review notes" --properties '{"description": "notes"}'
fptctl schema field-update Shot sg_review_notes --properties '{"visible": false}'
fptctl schema field-delete Shot sg_review_notes --yes
```

### Files

```shell
fptctl upload Shot 1234 plate.mov --field-name sg_uploaded_movie
fptctl thumbnail upload Shot 1234 thumb.png            # --filmstrip for a filmstrip image
fptctl thumbnail share Shot:1234 Shot:1235 --path thumb.png
fptctl thumbnail share Task:55 --source Shot:1234
fptctl download 941 -o plate.mov                       # or -o - for the raw bytes on stdout
fptctl attachment url 941
```

### Activity, notes, search and following

```shell
fptctl activity Shot 1234 --limit 20
fptctl note thread 5678
fptctl search sh010 --entity-types '{"Shot": []}' --project-id 70
fptctl follow HumanUser:42 Shot:1234
fptctl followers Shot:1234
fptctl following HumanUser:42 --project Project:70 --entity-type Shot
fptctl unfollow HumanUser:42 Shot:1234
```

### Everything else

Every public method of the library is reachable by name. Arguments are keyword arguments as JSON:

```shell
fptctl api methods
fptctl api call work_schedule_read --args '{"start_date": "2026-11-02", "end_date": "2026-11-06"}'
```

`fptctl info` shows the server version, and `fptctl auth token` prints a session token.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | unexpected error, including a value with no JSON form |
| 2 | usage error: bad options, unparsable JSON or filter, or the library rejected an argument |
| 3 | authentication failed, or there are no usable credentials |
| 4 | `get --must-exist` found nothing |
| 5 | the site reported an error (including permission errors) |
| 6 | network failure: connection, timeout, DNS or TLS |

When stderr is not a terminal, errors are one JSON object: `{"error": {"type", "message", "details"}}`.

## Shell completion

Add one line to your shell's startup file:

```shell
eval "$(_FPTCTL_COMPLETE=bash_source fptctl)"     # ~/.bashrc
eval "$(_FPTCTL_COMPLETE=zsh_source fptctl)"      # ~/.zshrc
_FPTCTL_COMPLETE=fish_source fptctl | source      # ~/.config/fish/completions/fptctl.fish
```

## Development

```shell
uv sync
git config core.hooksPath .githooks   # once per clone: keeps the skill docs current
uv run ruff format --check . && uv run ruff check . && uv run mypy src parity scripts
uv run pytest --cov=fptctl
```

Each command documents itself: its docstring has a summary, a description that names every
argument, and examples. `uv run python -m scripts.skill_docs` renders those docstrings into the
skill under `skills/fptctl/`. Tests fail when a command lacks any of them, when an example does not
parse, or when the generated files are stale, and CI runs the same checks on every push.

`parity/` checks every library method and parameter against a live sandbox site: it calls the library
directly and through `fptctl`, and compares both the requests and the results. It needs
`FPT_TEST_SITE`, `FPT_TEST_SCRIPT_NAME` and `FPT_TEST_API_KEY` (and `FPT_TEST_LOGIN` and
`FPT_TEST_PASSWORD` for the user-login cases), and it creates and then retires its own test data:

```shell
uv run python -m parity.runner
uv run python -m parity.burndown --strict
```

On GitHub, the **Parity** workflow runs the same suite on demand with the repository's secrets.
The **Library watch** workflow opens an issue when a new `shotgun_api3` release appears, and
pushing a `vX.Y.Z` tag drafts a release. The maintainer skills `skills/fptctl-library-upgrade` and
`skills/fptctl-release` describe those workflows. They are hidden from a normal `npx skills add`;
install them with `INSTALL_INTERNAL_SKILLS=1`.

## License

MIT. See [LICENSE](LICENSE).
