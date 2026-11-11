---
name: fptctl
description: Query and change a ShotGrid / Flow Production Tracking (FPT) site from the shell with the fptctl CLI. Covers finding, creating, updating and retiring entities (Shots, Assets, Tasks, Versions, Notes and the rest), reading and changing the schema, uploading and downloading files and thumbnails, activity streams, note threads, search, following, and calling any shotgun_api3 method. Use it whenever someone wants to read or change ShotGrid, Shotgun or FPT data, script against a studio's production tracking site, or install or sign in to fptctl, even if they never say "fptctl".
---

# fptctl

`fptctl` is a command-line interface for ShotGrid / Flow Production Tracking. It is a thin wrapper
around the official `shotgun_api3` library: each command makes one library call with the arguments
given and prints what the library returns. Piped output is JSON, so it suits scripts and agents.

## Install

Check first: `fptctl --version`. If it is missing, install it (Python 3.10 or newer):

```shell
uv tool install git+https://github.com/symbiote-labs/fptctl
# or: pip install git+https://github.com/symbiote-labs/fptctl
```

fptctl is not on PyPI; install it from GitHub as above. Two other projects have similar names.
`fpt-cli` on PyPI is unrelated. `dcc-mcp/fpt-cli` is a separate Rust ShotGrid CLI whose command
is `fpt`, with a different syntax (`fpt entity find ...`) and different environment variables;
none of it applies to fptctl. Until 0.2.0, fptctl itself was called `fpt`, so older notes may
use that name.

## Sign in

fptctl takes credentials from the first of: `--profile NAME`; the `FPTCTL_*` environment variables;
the profile named by `FPTCTL_PROFILE`; the default profile. Run `fptctl auth status` to see which
credentials are in use and whether they work.

- In a script or an agent session, prefer environment variables: `FPTCTL_SITE` with
  `FPTCTL_SCRIPT_NAME` and `FPTCTL_API_KEY` (an API script), or with `FPTCTL_LOGIN` and `FPTCTL_PASSWORD`,
  or with `FPTCTL_SESSION_TOKEN`.
- For a person at a terminal, `fptctl auth login` stores a named profile, with the secret in the OS
  keychain. On a machine with no keychain (a headless server), it fails; use the variables there.

Never print, log or echo a secret. If no credentials are set up, ask the user how they want to
sign in rather than guessing. [references/auth.md](references/auth.md) has the details: profiles,
2FA, proxies and CA bundles.

## How fptctl behaves

- **Output.** JSON when stdout is not a terminal, a table on a terminal; force one with
  `--format json|ndjson|table|csv`. JSON output is the library's return value unchanged.
  Datetimes are UTC text (`2026-11-10T14:30:00Z`).
- **Errors** go to stderr, as one JSON object `{"error": {"type", "message", "details"}}` when
  stderr is not a terminal.
- **Writes are safe to preview.** Every command that changes the site takes `--dry-run`, which
  makes no request and prints the library call it would make, as JSON:
  `{"call": "update", "args": {"entity_type": "Shot", "entity_id": 1234, "data": {...}}}`.
  Use it before any write you are unsure of, and check the `args` are what you meant.
- **Deletes are soft.** `delete` retires an entity and `revive` brings it back. `delete` and
  `schema field-delete` need `--yes` when stdin is not a terminal.
- **Missing is not an error.** `fptctl get TYPE ID` prints `null` and exits 0 for a missing entity,
  as the library does; add `--must-exist` to exit 4 instead.

| Exit | Meaning |
|---|---|
| 0 | success |
| 1 | unexpected error, including a value with no JSON form |
| 2 | usage error: bad options or JSON, or the library rejected an argument |
| 3 | authentication failed, or no usable credentials |
| 4 | `get --must-exist` found nothing |
| 5 | the site reported an error, including permission errors |
| 6 | network failure |

## Working with a site

1. Learn the data before you change it. Field names are site-specific (`sg_status_list`,
   `sg_cut_in`): list them with `fptctl schema fields TYPE`, and look at a few real entities with
   `fptctl find TYPE --limit 3 --fields ...`.
2. Filter on the server, not in a script: `fptctl find Shot -f 'project is Project:70' -f
   'sg_status_list in ["ip","rev"]'`. The filter and `--set` shorthand is in
   [references/filters-and-data.md](references/filters-and-data.md). Read it before writing
   filters or field values, because it decides whether a value is sent as a number, a string or
   an entity link.
3. Preview writes with `--dry-run`, then run them. For several related writes, `fptctl batch`
   applies them in one transaction.
4. For anything without a command of its own, `fptctl api methods` lists every library method and
   `fptctl api call METHOD --args JSON` calls it.

## Global options

These go before the command name: `fptctl --format csv find Shot`.

<!-- BEGIN GENERATED: global-options (scripts/skill_docs.py; edit the CLI docstrings instead) -->
- `--profile TEXT`: Named profile to use (see `fptctl auth list`).
- `--site TEXT`: Site URL; overrides the profile or FPTCTL_SITE.
- `--format [json|ndjson|table|csv]`: Output format.
- `--sudo-as LOGIN`: Act as this user (script auth only).
- `--no-color`: Disable coloured output.
- `--verbose`: Log API requests to stderr.
- `--version`: Show the version and exit.
<!-- END GENERATED: global-options -->

## Commands

Each line is the command's usage and summary. Open the linked reference for a command's
description, every option, the library method it calls, and examples. `fptctl COMMAND --help`
prints the same text.

<!-- BEGIN GENERATED: commands (scripts/skill_docs.py; edit the CLI docstrings instead) -->
**Activity commands**: [references/commands/activity.md](references/commands/activity.md)
- `fptctl activity [OPTIONS] TYPE ID`: Read the activity stream of entity ID of TYPE.
- `fptctl note thread [OPTIONS] NOTE_ID`: Read a Note's thread: its Replies and Attachments.
- `fptctl search [OPTIONS] TEXT`: Search entity names for TEXT.

**API commands**: [references/commands/api.md](references/commands/api.md)
- `fptctl api call [OPTIONS] METHOD`: Call METHOD with keyword arguments and print its return value.
- `fptctl api methods [OPTIONS]`: List the library's public methods and their signatures.

**Auth commands**: [references/commands/auth.md](references/commands/auth.md)
- `fptctl auth list [OPTIONS]`: List the stored profiles.
- `fptctl auth login [OPTIONS]`: Store credentials for a site as a named profile.
- `fptctl auth logout [OPTIONS] [NAME]`: Remove a profile and its stored secret.
- `fptctl auth status [OPTIONS]`: Check that the current credentials work.
- `fptctl auth token [OPTIONS]`: Print a session token for the current credentials.
- `fptctl auth use [OPTIONS] NAME`: Make NAME the default profile.

**Batch command**: [references/commands/batch.md](references/commands/batch.md)
- `fptctl batch [OPTIONS] [FILE]`: Run create, update and delete requests from FILE in one transaction.

**Entity commands**: [references/commands/entity.md](references/commands/entity.md)
- `fptctl create [OPTIONS] TYPE`: Create an entity of TYPE.
- `fptctl delete [OPTIONS] TYPE ID`: Retire (soft-delete) entity ID of TYPE.
- `fptctl find [OPTIONS] TYPE`: Find entities of TYPE.
- `fptctl get [OPTIONS] TYPE ID`: Get one entity of TYPE by ID.
- `fptctl revive [OPTIONS] TYPE ID`: Revive a retired entity ID of TYPE.
- `fptctl update [OPTIONS] TYPE ID`: Update entity ID of TYPE.

**File commands**: [references/commands/files.md](references/commands/files.md)
- `fptctl attachment url [OPTIONS] ATTACHMENT`: Print the download URL of ATTACHMENT.
- `fptctl download [OPTIONS] ATTACHMENT`: Download ATTACHMENT to a file or to stdout.
- `fptctl thumbnail share [OPTIONS] ENTITY...`: Give every ENTITY the same thumbnail.
- `fptctl thumbnail upload [OPTIONS] TYPE ID PATH`: Set the thumbnail of entity ID of TYPE from the image at PATH.
- `fptctl upload [OPTIONS] TYPE ID PATH`: Upload the file at PATH to entity ID of TYPE.

**Schema commands**: [references/commands/schema.md](references/commands/schema.md)
- `fptctl schema entities [OPTIONS]`: List every entity type and its properties.
- `fptctl schema field-create [OPTIONS] TYPE DATA_TYPE DISPLAY_NAME`: Create a field on TYPE and print its name.
- `fptctl schema field-delete [OPTIONS] TYPE FIELD`: Delete FIELD from TYPE.
- `fptctl schema field-update [OPTIONS] TYPE FIELD`: Change the properties of FIELD on TYPE.
- `fptctl schema fields [OPTIONS] TYPE [FIELD]`: Read the fields of TYPE, or only FIELD.
- `fptctl schema read [OPTIONS]`: Read the whole schema: every field of every entity type.

**Site commands**: [references/commands/site.md](references/commands/site.md)
- `fptctl info [OPTIONS]`: Show the server's version and capabilities.

**Follow commands**: [references/commands/social.md](references/commands/social.md)
- `fptctl follow [OPTIONS] USER ENTITY`: Make USER follow ENTITY.
- `fptctl followers [OPTIONS] ENTITY`: List the users who follow ENTITY.
- `fptctl following [OPTIONS] USER`: List the entities USER follows.
- `fptctl unfollow [OPTIONS] USER ENTITY`: Make USER stop following ENTITY.

**Summarize command**: [references/commands/summarize.md](references/commands/summarize.md)
- `fptctl summarize [OPTIONS] TYPE`: Summarize fields of the TYPE entities that match the filters.
<!-- END GENERATED: commands -->
