# Filters, field values and JSON input

These rules decide what type a value is sent as. Getting them wrong sends a number where the
site expects a string, or text where it expects an entity link, so read them before building a
filter or a `--set`.

## Filters: `-f 'FIELD OP VALUE'`

Used by `find`, `summarize`, and anything else with `-f`. Repeat `-f` to AND conditions; add
`--any` to OR them instead.

The text is split at the first two runs of whitespace, so everything after the operator is
VALUE. VALUE is then read with three rules, in order:

1. If VALUE is valid JSON, it is that JSON value: `5`, `true`, `null`, `"101"`, `["ip","rev"]`,
   `{"type":"Project","id":70}`.
2. If VALUE looks like `Type:123` (a capitalised type, a colon, digits), it is an entity link.
3. Otherwise VALUE is the literal text.

| Filter | Sends |
|---|---|
| `-f 'code is 101'` | `["code", "is", 101]` (a number) |
| `-f 'code is "101"'` | `["code", "is", "101"]` (a string) |
| `-f 'code is sh010'` | `["code", "is", "sh010"]` |
| `-f 'project is Project:70'` | `["project", "is", {"type": "Project", "id": 70}]` |
| `-f 'sg_status_list in ["ip","rev"]'` | `["sg_status_list", "in", ["ip", "rev"]]` |
| `-f 'description is null'` | `["description", "is", null]` |
| `-f 'created_at in_last [3,"DAY"]'` | `["created_at", "in_last", 3, "DAY"]` (spread) |
| `-f 'sg_cut_in between [1001,1100]'` | `["sg_cut_in", "between", 1001, 1100]` (spread) |

A JSON array is spread into separate arguments only for `between`, `not_between`, `in_last`,
`not_in_last`, `in_next` and `not_in_next`. For every other operator an array is one value.
There is no comma splitting: `-f 'code in a,b'` sends the text `a,b`.

Which operators a field accepts depends on its data type (`fptctl schema fields TYPE FIELD` shows
the type). The server rejects an operator the type does not support, with exit 5.

### Raw filters

`--filters` takes the API's own filter structure, as JSON, `@FILE` or `-` for stdin, and cannot
be mixed with `-f`. Use it for nested logic:

```shell
fptctl find Shot --filters '{"filter_operator": "any", "filters": [["code", "is", "sh010"], ["code", "is", "sh020"]]}'
```

## Field values: `--set` and `--data`

For `create` and `update`:

- `--set FIELD=TEXT` always sends a string: `--set code=010` sends `"010"`.
- `--set FIELD:=JSON` sends a typed value: `--set sg_cut_in:=1001`, `--set 'tags:=[]'`,
  `--set 'project:={"type": "Project", "id": 70}'`.
- `--data JSON|@FILE|-` gives a whole object. `--set` values override `--data` keys.

## JSON input everywhere

Wherever fptctl reads JSON (`--data`, `--set field:=`, `--filters`, `--args` and the other JSON
options):

- `{"$datetime": "2026-11-10T14:30:00Z"}` becomes a datetime (UTC with `Z`, local without it).
  Nothing else is special.
- Dates are plain `"YYYY-MM-DD"` strings, as the API takes them.
- Options shown as `JSON|@FILE|-` also read a file (`@path.json`) or stdin (`-`).

## Output values

JSON output uses the same forms: datetimes come back as UTC text ending in `Z`, dates as
`YYYY-MM-DD`, entity links as `{"type", "id", "name"}` objects. Bytes are never JSON: `download`
writes them to a file, or raw to stdout with `-o -`.
