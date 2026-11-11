---
name: fpt
description: Query and change a ShotGrid / Flow Production Tracking (FPT) site from the shell with the fpt CLI. Covers finding, creating, updating and retiring entities (Shots, Assets, Tasks, Versions, Notes and the rest), reading and changing the schema, uploading and downloading files and thumbnails, activity streams, note threads, search, following, and calling any shotgun_api3 method. Use it whenever someone wants to read or change ShotGrid, Shotgun or FPT data, script against a studio's production tracking site, or install or sign in to fpt, even if they never say "fpt".
---

# fpt

`fpt` is a command-line interface for ShotGrid / Flow Production Tracking. It is a thin wrapper
around the official `shotgun_api3` library: each command makes one library call with the arguments
given and prints what the library returns. Piped output is JSON, so it suits scripts and agents.

## Install

Check first: `fpt --version`. If it is missing, install it (Python 3.10 or newer):

```shell
uv tool install git+https://github.com/symbiote-labs/fpt-cli
# or: pip install git+https://github.com/symbiote-labs/fpt-cli
```

## Sign in

fpt takes credentials from the first of: `--profile NAME`; the `FPT_*` environment variables;
the profile named by `FPT_PROFILE`; the default profile. Run `fpt auth status` to see which
credentials are in use and whether they work.

- In a script or an agent session, prefer environment variables: `FPT_SITE` with
  `FPT_SCRIPT_NAME` and `FPT_API_KEY` (an API script), or with `FPT_LOGIN` and `FPT_PASSWORD`,
  or with `FPT_SESSION_TOKEN`.
- For a person at a terminal, `fpt auth login` stores a named profile, with the secret in the OS
  keychain. On a machine with no keychain (a headless server), it fails; use the variables there.

Never print, log or echo a secret. If no credentials are set up, ask the user how they want to
sign in rather than guessing. [references/auth.md](references/auth.md) has the details: profiles,
2FA, proxies and CA bundles.

## How fpt behaves

- **Output.** JSON when stdout is not a terminal, a table on a terminal; force one with
  `--format json|ndjson|table|csv`. JSON output is the library's return value unchanged.
  Datetimes are UTC text (`2026-11-10T14:30:00Z`).
- **Errors** go to stderr, as one JSON object `{"error": {"type", "message", "details"}}` when
  stderr is not a terminal.
- **Writes are safe to preview.** Every command that changes the site takes `--dry-run`, which
  prints the library call and makes no request. Use it before any write you are unsure of.
- **Deletes are soft.** `delete` retires an entity and `revive` brings it back. `delete` and
  `schema field-delete` need `--yes` when stdin is not a terminal.
- **Missing is not an error.** `fpt get TYPE ID` prints `null` and exits 0 for a missing entity,
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
   `sg_cut_in`): list them with `fpt schema fields TYPE`, and look at a few real entities with
   `fpt find TYPE --limit 3 --fields ...`.
2. Filter on the server, not in a script: `fpt find Shot -f 'project is Project:70' -f
   'sg_status_list in ["ip","rev"]'`. The filter and `--set` shorthand is in
   [references/filters-and-data.md](references/filters-and-data.md). Read it before writing
   filters or field values, because it decides whether a value is sent as a number, a string or
   an entity link.
3. Preview writes with `--dry-run`, then run them. For several related writes, `fpt batch`
   applies them in one transaction.
4. For anything without a command of its own, `fpt api methods` lists every library method and
   `fpt api call METHOD --args JSON` calls it.

## Global options

These go before the command name: `fpt --format csv find Shot`.

<!-- BEGIN GENERATED: global-options (scripts/skill_docs.py; edit the CLI docstrings instead) -->
- `--profile TEXT`: Named profile to use (see `fpt auth list`).
- `--site TEXT`: Site URL; overrides the profile or FPT_SITE.
- `--format [json|ndjson|table|csv]`: Output format.
- `--sudo-as LOGIN`: Act as this user (script auth only).
- `--no-color`: Disable coloured output.
- `--verbose`: Log API requests to stderr.
- `--version`: Show the version and exit.
<!-- END GENERATED: global-options -->

## Commands

Each line is the command's usage and summary. Open the linked reference for a command's
description, every option, the library method it calls, and examples. `fpt COMMAND --help`
prints the same text.

<!-- BEGIN GENERATED: commands (scripts/skill_docs.py; edit the CLI docstrings instead) -->
**Activity commands**: [references/commands/activity.md](references/commands/activity.md)
- `fpt activity [OPTIONS] TYPE ID`: Read the activity stream of entity ID of TYPE.
- `fpt note thread [OPTIONS] NOTE_ID`: Read a Note's thread: its Replies and Attachments.
- `fpt search [OPTIONS] TEXT`: Search entity names for TEXT.

**API commands**: [references/commands/api.md](references/commands/api.md)
- `fpt api call [OPTIONS] METHOD`: Call METHOD with keyword arguments and print its return value.
- `fpt api methods [OPTIONS]`: List the library's public methods and their signatures.

**Auth commands**: [references/commands/auth.md](references/commands/auth.md)
- `fpt auth list [OPTIONS]`: List the stored profiles.
- `fpt auth login [OPTIONS]`: Store credentials for a site as a named profile.
- `fpt auth logout [OPTIONS] [NAME]`: Remove a profile and its stored secret.
- `fpt auth status [OPTIONS]`: Check that the current credentials work.
- `fpt auth token [OPTIONS]`: Print a session token for the current credentials.
- `fpt auth use [OPTIONS] NAME`: Make NAME the default profile.

**Batch command**: [references/commands/batch.md](references/commands/batch.md)
- `fpt batch [OPTIONS] [FILE]`: Run create, update and delete requests from FILE in one transaction.

**Entity commands**: [references/commands/entity.md](references/commands/entity.md)
- `fpt create [OPTIONS] TYPE`: Create an entity of TYPE.
- `fpt delete [OPTIONS] TYPE ID`: Retire (soft-delete) entity ID of TYPE.
- `fpt find [OPTIONS] TYPE`: Find entities of TYPE.
- `fpt get [OPTIONS] TYPE ID`: Get one entity of TYPE by ID.
- `fpt revive [OPTIONS] TYPE ID`: Revive a retired entity ID of TYPE.
- `fpt update [OPTIONS] TYPE ID`: Update entity ID of TYPE.

**File commands**: [references/commands/files.md](references/commands/files.md)
- `fpt attachment url [OPTIONS] ATTACHMENT`: Print the download URL of ATTACHMENT.
- `fpt download [OPTIONS] ATTACHMENT`: Download ATTACHMENT to a file or to stdout.
- `fpt thumbnail share [OPTIONS] ENTITY...`: Give every ENTITY the same thumbnail.
- `fpt thumbnail upload [OPTIONS] TYPE ID PATH`: Set the thumbnail of entity ID of TYPE from the image at PATH.
- `fpt upload [OPTIONS] TYPE ID PATH`: Upload the file at PATH to entity ID of TYPE.

**Schema commands**: [references/commands/schema.md](references/commands/schema.md)
- `fpt schema entities [OPTIONS]`: List every entity type and its properties.
- `fpt schema field-create [OPTIONS] TYPE DATA_TYPE DISPLAY_NAME`: Create a field on TYPE and print its name.
- `fpt schema field-delete [OPTIONS] TYPE FIELD`: Delete FIELD from TYPE.
- `fpt schema field-update [OPTIONS] TYPE FIELD`: Change the properties of FIELD on TYPE.
- `fpt schema fields [OPTIONS] TYPE [FIELD]`: Read the fields of TYPE, or only FIELD.
- `fpt schema read [OPTIONS]`: Read the whole schema: every field of every entity type.

**Site commands**: [references/commands/site.md](references/commands/site.md)
- `fpt info [OPTIONS]`: Show the server's version and capabilities.

**Follow commands**: [references/commands/social.md](references/commands/social.md)
- `fpt follow [OPTIONS] USER ENTITY`: Make USER follow ENTITY.
- `fpt followers [OPTIONS] ENTITY`: List the users who follow ENTITY.
- `fpt following [OPTIONS] USER`: List the entities USER follows.
- `fpt unfollow [OPTIONS] USER ENTITY`: Make USER stop following ENTITY.

**Summarize command**: [references/commands/summarize.md](references/commands/summarize.md)
- `fpt summarize [OPTIONS] TYPE`: Summarize fields of the TYPE entities that match the filters.
<!-- END GENERATED: commands -->
