# fptctl

A command line for ShotGrid (Flow Production Tracking). Each command makes one call to Autodesk's
[`shotgun_api3`](https://github.com/shotgunsoftware/python-api) library with the arguments you
give it, and prints what the library returns. It doesn't add, rename or reshape anything on the
way out, so if you know the Python API, you already know what you'll get back.

It works the same for a person at a terminal, a shell script, or an AI agent: tables on a
terminal, JSON when piped, stable exit codes, and no prompts when nobody's there to answer them.

## Install

You need Python 3.10 or newer.

```shell
uv tool install git+https://github.com/symbiote-labs/fptctl@v0.2.0
# or: pip install git+https://github.com/symbiote-labs/fptctl@v0.2.0
fptctl --version
```

From a checkout, `uv tool install .` works too.

## Keeping up with the library

fptctl pins one exact release of the library, `shotgun_api3` 3.10.5. That's the version its parity
suite has checked, method by method, against a live site.

A workflow checks PyPI every day. When Autodesk ships a new release, it compares the public API
of the two versions and opens an issue listing every method and parameter that was added,
removed or changed. That list is the to-do list for the upgrade. The upgrade itself is done by
hand, and a new fptctl only goes out once parity passes against the new library. So fptctl
might lag a new release by a bit, but it won't ship a version nobody tested against a real site.

## Agent skill

If you use an AI coding agent, this adds a skill that teaches it how to install and drive
fptctl:

```shell
npx skills add symbiote-labs/fptctl --skill fptctl
```

The skill's command reference is generated from the same docstrings as `fptctl --help`, and CI
fails if they drift apart.

## Authentication

Save your credentials once as a named profile. The site and settings go to
`~/.config/fptctl/config.toml`, and the secret goes to the OS keychain.

```shell
fptctl auth login --site https://studio.shotgrid.autodesk.com --script-name my_script   # API script
fptctl auth login --name me --site https://studio.shotgrid.autodesk.com --login jane       # user login
# With 2FA: stores a session, not your password
fptctl auth login --name me --site https://studio.shotgrid.autodesk.com --login jane --otp 123456
fptctl auth list
fptctl auth use me      # make "me" the default
fptctl auth status      # check the credentials work
fptctl auth logout me
```

`auth login` asks for the secret, or reads it from stdin when stdin isn't a terminal.

On a headless server (or anywhere without a keychain), use environment variables instead:
`FPTCTL_SITE` plus either `FPTCTL_SCRIPT_NAME` and `FPTCTL_API_KEY`, `FPTCTL_LOGIN` and
`FPTCTL_PASSWORD`, or `FPTCTL_SESSION_TOKEN`. `FPTCTL_HTTP_PROXY` and `FPTCTL_CA_CERTS` are there
if you need them.

fptctl uses the first of these it finds: `--profile NAME`, the environment variables, the profile
named in `FPTCTL_PROFILE`, then your default profile. `--site` overrides the site in any of them.

## Output

Results go to stdout and everything else to stderr. You get a table on a terminal and JSON
otherwise, or pick one with `--format json|ndjson|table|csv`.

Datetimes come out as UTC text (`2026-11-10T14:30:00Z`). To send one in, anywhere fptctl takes
JSON, write `{"$datetime": "2026-11-10T14:30:00Z"}`. Dates are plain `YYYY-MM-DD`. An option
shown as `JSON|@FILE|-` in `--help` also reads a file (`@FILE`) or stdin (`-`).

## Commands

`fptctl COMMAND --help` has every option, with examples.

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
fptctl batch requests.ndjson                # creates, updates and deletes in one transaction
fptctl summarize Shot -f 'project is Project:70' --summary-fields '[{"field":"id","type":"count"}]'
```

Each `-f 'FIELD OP VALUE'` is ANDed with the others (`--any` ORs them). The value is read as JSON
if it parses (`5`, `true`, `["ip","rev"]`), as a link if it looks like `Type:123`, and as text
otherwise. That means `code is 101` sends a number and `code is "101"` sends a string. For
`between`, `in_last` and `in_next`, give the arguments as an array:
`-f 'created_at in_last [3,"DAY"]'`. If you'd rather write the raw API filter structure, use
`--filters` (but not together with `-f`).

`--set field=value` sets text, `--set field:=JSON` sets a typed value, and `--data` takes a whole
object. Where they overlap, `--set` wins.

`delete` and `schema field-delete` ask before deleting on a terminal, and need `--yes` in a
script. Every command that writes takes `--dry-run`, which prints the library call it would make
without sending it.

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
fptctl download 941 -o plate.mov                       # -o - writes the bytes to stdout
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

Every public method in the library is reachable by name, with its keyword arguments as JSON:

```shell
fptctl api methods
fptctl api call work_schedule_read --args '{"start_date": "2026-11-02", "end_date": "2026-11-06"}'
```

`fptctl info` shows the server version, and `fptctl auth token` prints a session token. Other
global options: `--sudo-as LOGIN`, `--verbose` (logs requests to stderr) and `--no-color`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | unexpected error, including a value with no JSON form |
| 2 | usage error: bad options, bad JSON or filter, or the library rejected an argument |
| 3 | authentication failed, or no usable credentials |
| 4 | `get --must-exist` found nothing |
| 5 | the site reported an error (including permission errors) |
| 6 | network failure: connection, timeout, DNS or TLS |

When stderr isn't a terminal, an error is a single JSON object:
`{"error": {"type", "message", "details"}}`.

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

Every command's docstring has a summary, a description of each argument, and examples that have
to parse. `uv run python -m scripts.skill_docs` turns them into the skill under `skills/fptctl/`,
and the tests fail if anything's missing or stale.

`parity/` is how I know fptctl does what the library does. It calls every library method twice,
once directly and once through fptctl, against a sandbox site, and compares the requests and the
results. It needs `FPT_TEST_SITE`, `FPT_TEST_SCRIPT_NAME` and `FPT_TEST_API_KEY` (plus
`FPT_TEST_LOGIN` and `FPT_TEST_PASSWORD` for the user-login cases), and it cleans up the test data
it creates:

```shell
uv run python -m parity.runner
uv run python -m parity.burndown --strict
```

On GitHub, the Parity workflow runs the same thing on demand, and pushing a `vX.Y.Z` tag drafts a
release. The maintainer skills for upgrading the library and releasing are in `skills/`, hidden
from a normal `npx skills add` (install them with `INSTALL_INTERNAL_SKILLS=1`).

## License

MIT. See [LICENSE](LICENSE).
