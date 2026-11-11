# fpt

A command-line interface for ShotGrid / Flow Production Tracking. `fpt` is a thin wrapper around the
official [`shotgun_api3`](https://github.com/shotgunsoftware/python-api) library: each command makes
one library call with the arguments you give it and prints what the library returns.

It is built for people, scripts and AI agents alike: JSON when piped, tables on a terminal, stable exit
codes, and no prompts when stdin is not a terminal.

`fpt` is built on `shotgun_api3` 3.10.5 and pins that exact release, the one its parity suite verifies
against a live site (see Development).

## Install

`fpt` needs Python 3.10 or newer.

```shell
uv tool install git+https://github.com/symbiote-labs/fpt-cli@v0.1.0
# or: pip install git+https://github.com/symbiote-labs/fpt-cli@v0.1.0
fpt --version
```

From a checkout, `uv tool install .` (or `pip install .`).

## Authentication

Store credentials once as a named profile. The site and the non-secret settings go to
`~/.config/fpt/config.toml` (or `$XDG_CONFIG_HOME/fpt/config.toml`, or the path in `FPT_CONFIG`); the
secret goes to the OS keychain under the service `fpt`.

```shell
fpt auth login --site https://studio.shotgrid.autodesk.com --script-name my_script   # API script
fpt auth login --name me --site https://studio.shotgrid.autodesk.com --login jane       # user login
# With 2FA: stores a session, not the password
fpt auth login --name me --site https://studio.shotgrid.autodesk.com --login jane --otp 123456
fpt auth list        # profiles
fpt auth use me      # make "me" the default
fpt auth status      # check the current credentials work
fpt auth logout me
```

`auth login` reads the secret (API key, password, or session token with `--session`) from a prompt, or
from stdin when stdin is not a terminal. `--http-proxy` and `--ca-certs` are stored with the profile.

Credentials are taken from the first of:

1. `--profile NAME`;
2. environment variables: `FPT_SITE` with `FPT_SCRIPT_NAME` and `FPT_API_KEY`, or with `FPT_LOGIN`
   and `FPT_PASSWORD`, or with `FPT_SESSION_TOKEN`;
3. the profile named by `FPT_PROFILE`;
4. the default profile.

`--site` overrides the site from any of these. With the environment variables, `FPT_HTTP_PROXY` and
`FPT_CA_CERTS` set the proxy and the CA bundle; a profile uses the ones stored with it.

On a machine with no keychain backend (a headless Linux server, for one) `auth login` fails with a
keychain error. Use the environment variables there instead.

## Output

Results go to stdout and everything else to stderr. The default format is `table` on a terminal and
`json` otherwise; choose one with `--format json|ndjson|table|csv`. JSON output is the library's
return value, with nothing added, removed or renamed.

Values are written as JSON, and timezone-aware datetimes as UTC text (`2026-11-10T14:30:00Z`). Wherever `fpt` reads
JSON (`--data`, `--set field:=`, `--filters`, `api call --args` and the other JSON options), the
object `{"$datetime": "2026-11-10T14:30:00Z"}` becomes a datetime. Dates are plain `YYYY-MM-DD`
strings. Options shown as `JSON|@FILE|-` in `--help` also read a file (`@FILE`) or stdin (`-`).

Other global options: `--sudo-as LOGIN` (act as a user, with script credentials), `--verbose` (log
requests to stderr), `--no-color`.

## Commands

Run `fpt COMMAND --help` for every option.

### Find and change entities

```shell
fpt find Shot -f 'project is Project:70' -f 'sg_status_list in ["ip","rev"]' --fields code,sg_status_list
fpt find Shot --filters @filters.json --order -created_at --limit 10
fpt get Shot 1234 --fields code
fpt get Shot 1234 --must-exist           # exit 4 instead of printing null
fpt create Shot --set code=sh010 --set 'project:={"type":"Project","id":70}'
fpt update Shot 1234 --set sg_cut_in:=1001 --data @more.json
fpt delete Shot 1234 --yes
fpt revive Shot 1234
fpt batch requests.ndjson                # create/update/delete requests in one transaction
fpt summarize Shot -f 'project is Project:70' --summary-fields '[{"field":"id","type":"count"}]'
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
fpt schema entities
fpt schema fields Shot sg_status_list --project Project:70
fpt schema field-create Shot text "Review notes" --properties '{"description": "notes"}'
fpt schema field-update Shot sg_review_notes --properties '{"visible": false}'
fpt schema field-delete Shot sg_review_notes --yes
```

### Files

```shell
fpt upload Shot 1234 plate.mov --field-name sg_uploaded_movie
fpt thumbnail upload Shot 1234 thumb.png            # --filmstrip for a filmstrip image
fpt thumbnail share Shot:1234 Shot:1235 --path thumb.png
fpt thumbnail share Task:55 --source Shot:1234
fpt download 941 -o plate.mov                       # or -o - for the raw bytes on stdout
fpt attachment url 941
```

### Activity, notes, search and following

```shell
fpt activity Shot 1234 --limit 20
fpt note thread 5678
fpt search sh010 --entity-types '{"Shot": []}' --project-id 70
fpt follow HumanUser:42 Shot:1234
fpt followers Shot:1234
fpt following HumanUser:42 --project Project:70 --entity-type Shot
fpt unfollow HumanUser:42 Shot:1234
```

### Everything else

Every public method of the library is reachable by name. Arguments are keyword arguments as JSON:

```shell
fpt api methods
fpt api call work_schedule_read --args '{"start_date": "2026-11-02", "end_date": "2026-11-06"}'
```

`fpt info` shows the server version, and `fpt auth token` prints a session token.

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
eval "$(_FPT_COMPLETE=bash_source fpt)"     # ~/.bashrc
eval "$(_FPT_COMPLETE=zsh_source fpt)"      # ~/.zshrc
_FPT_COMPLETE=fish_source fpt | source      # ~/.config/fish/completions/fpt.fish
```

## Development

```shell
uv sync
uv run ruff format --check . && uv run ruff check . && uv run mypy src parity
uv run pytest --cov=fpt
```

`parity/` checks every library method and parameter against a live sandbox site: it calls the library
directly and through `fpt`, and compares both the requests and the results. It needs
`FPT_TEST_SITE`, `FPT_TEST_SCRIPT_NAME` and `FPT_TEST_API_KEY` (and `FPT_TEST_LOGIN` and
`FPT_TEST_PASSWORD` for the user-login cases), and it creates and then retires its own test data:

```shell
uv run python -m parity.runner
uv run python -m parity.burndown --strict
```

## License

MIT. See [LICENSE](LICENSE).
