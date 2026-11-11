"""Write the data-driven parity cases: field-read, field-write, filter-op and enum-value.

The spec says these cases "are generated from dimensions.toml and the live schema, not written
one by one". `uv run python -m parity.generate` reads the schema snapshot in results/latest.json,
dimensions.toml and waivers.toml, and writes parity/cases/generated_*.json. The output is
committed, so a case is still data the runner reads; a unit test fails when it is stale.

Values come from the run's fixtures through placeholders (`${twin.id}`, `${dates.future}`, ...),
so each case matches at least one fixture row.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from parity import fixtures
from parity.burndown import LATEST, WAIVERS_PATH, load_waivers
from parity.inventory import compute_items, load_dimensions

CASES_DIR = Path(__file__).resolve().parent / "cases"
IMAGE_PATH = "parity/assets/fpt-parity.png"  # relative to the repository root, where both run
SHOT, TASK = fixtures.FIELD_ENTITY, fixtures.TASK_ENTITY
# The first item of these kinds is a hand-written case (parity/cases/batch.json).
HAND_WRITTEN = frozenset(
    {
        "enum-value:batch_request_type.create",
        "enum-value:batch_request_type.update",
        "enum-value:batch_request_type.delete",
    }
)
GENERATED_KINDS = ("field-read", "field-write", "filter-op", "enum-value")

# Placeholders that stand for a JSON object or a number, written unquoted in command-line text.
_RAW = ("${project}", "${project.id}", "${dates.day}", "${dates.week}", "${dates.month}",
        "${dates.year}")  # fmt: skip
PROJECT_LINK: dict[str, Any] = {"type": "Project", "id": "${project.id}"}
_LINKS = {
    "project": "${project}",
    "dates": {"future": "${dates.future}", "future_time": "${dates.future_time}"},
}
_ORDER_BY_ID = [{"field_name": "id", "direction": "asc"}]
_NONE = "fpt_parity_none"  # matches no fixture value

Entry = tuple[str, dict[str, Any]]  # (the item the case is for, the case)


def text(value: Any) -> str:
    """`value` as command-line JSON, with object and number placeholders unquoted."""
    rendered = json.dumps(value)
    for placeholder in _RAW:
        rendered = rendered.replace(json.dumps(placeholder), placeholder)
    return rendered


def parity_template(data_type: str) -> Any:
    """The fixture value of a parity field, as case data (placeholders, typed input)."""
    properties = fixtures._CREATE_PROPERTIES.get(data_type, {})
    schema = {"properties": {"valid_values": {"value": properties.get("valid_values")}}}
    value = fixtures.sample_value(data_type, schema, _LINKS)
    if data_type == "date_time":
        return {"$datetime": value}
    if data_type == "multi_entity":
        return [value[0]]
    return value


def _case(case_id: str, method: str, mode: str, args: dict[str, Any], argv: list[str],
          **extra: Any) -> dict[str, Any]:  # fmt: skip
    return {"id": case_id, "method": method, "mode": mode, "args": args, "argv": argv, **extra}


def _project_filter() -> tuple[list[Any], list[str]]:
    return ["project", "is", PROJECT_LINK], ["-f", "project is Project:${project.id}"]


# --- field-read ------------------------------------------------------------------------------

# Data types no parity field holds: where a non-null value is read. A role reads that fixture by
# id; "not_null" filters on the field; "first" takes the first row (the type cannot be filtered).
EXTRA_READS: dict[str, tuple[str, str, str]] = {
    "calculated": ("Task", "workload", "not_null"),
    "color": (TASK, "color", "task"),
    "entity_type": ("Page", "entity_type", "not_null"),
    "image": (SHOT, "image", "not_null"),
    "password": ("HumanUser", "password_proxy", "first"),
    "serializable": (TASK, "splits", "task"),
    "summary": (SHOT, "open_notes_count", "twin"),
    "uuid": ("Icon", "uuid", "first"),
}


def _read(case_id: str, entity: str, field: str, scope: str) -> dict[str, Any]:
    args: dict[str, Any] = {"entity_type": entity, "fields": [field]}
    argv = ["find", entity]
    if scope in ("not_null", "first"):
        args["filters"] = [[field, "is_not", None]] if scope == "not_null" else []
        argv += ["-f", f"{field} is_not null"] if scope == "not_null" else []
        args.update(order=_ORDER_BY_ID, limit=1)
        argv += ["--fields", field, "--order", "id", "--limit", "1"]
    else:
        args["filters"] = [["id", "is", f"${{{scope}.id}}"]]
        argv += ["-f", f"id is ${{{scope}.id}}", "--fields", field]
    return _case(case_id, "find", "identical", args, argv)


def field_read(data_type: str, parity: set[str]) -> dict[str, Any] | None:
    case_id = f"field_read.{data_type}"
    if data_type in parity:
        return _read(case_id, SHOT, fixtures.field_name(data_type), "twin")
    if data_type in EXTRA_READS:
        return _read(case_id, *EXTRA_READS[data_type])
    return None


# --- field-write -----------------------------------------------------------------------------

EXTRA_WRITES: dict[str, tuple[str, str, str, Any]] = {
    "color": (TASK, "task", "color", fixtures.TASK_VALUES["color"]),
    "serializable": (TASK, "task", "splits", fixtures.TASK_VALUES["splits"]),
    "image": (SHOT, "twin", "image", IMAGE_PATH),
}


def field_write(data_type: str, parity: set[str]) -> dict[str, Any] | None:
    if data_type in parity:
        entity, role = SHOT, "twin"
        field, value = fixtures.field_name(data_type), parity_template(data_type)
    elif data_type in EXTRA_WRITES:
        entity, role, field, value = EXTRA_WRITES[data_type]
    else:
        return None
    # The image path is text; the library uploads it. Every other value is typed JSON.
    setting = f"{field}={value}" if data_type == "image" else f"{field}:={text(value)}"
    return _case(
        f"field_write.{data_type}",
        "update",
        "mirrored",
        {"entity_type": entity, "entity_id": f"${{{role}.id}}", "data": {field: value}},
        ["update", entity, f"${{{role}.id}}", "--set", setting],
        readback={"entity": f"${{{role}}}", "fields": [field]},
        masks=["id"],
    )


# --- filter-op -------------------------------------------------------------------------------

# value, a larger value, a smaller value (each matches or misses the twins' value)
_NUMBERS = {"number": (7, 8, 6), "float": (1.5, 2.5, 0.5), "duration": (90, 91, 89),
            "percent": (50, 51, 49)}  # fmt: skip
_LAST_NEXT = [40, "DAY"]  # the run's dates are 28 days away


def _dates(data_type: str) -> tuple[Any, Any]:
    if data_type == "date":
        return "${dates.future}", "${dates.past}"
    return {"$datetime": "${dates.future_time}"}, {"$datetime": "${dates.past_time}"}


def filter_value(data_type: str, operator: str) -> Any:
    """A VALUE that matches at least one fixture row in the run project."""
    if data_type in _NUMBERS:
        value, above, below = _NUMBERS[data_type]
        table: dict[str, Any] = {"is": value, "is_not": above, "less_than": above,
                                 "greater_than": below, "between": [below, above],
                                 "not_between": [above, above + 1], "in": [value],
                                 "not_in": [above]}  # fmt: skip
    elif data_type in fixtures.DATE_TYPES:
        future, past = _dates(data_type)
        table = {"is": future, "is_not": past, "less_than": future, "greater_than": past,
                 "between": [past, future], "in": [future], "not_in": [past],
                 "in_last": _LAST_NEXT, "not_in_last": _LAST_NEXT, "in_next": _LAST_NEXT,
                 "not_in_next": _LAST_NEXT, "in_calendar_day": "${dates.day}",
                 "in_calendar_week": "${dates.week}", "in_calendar_month": "${dates.month}",
                 "in_calendar_year": "${dates.year}"}  # fmt: skip
    elif data_type in ("entity", "multi_entity"):
        table = {"is": PROJECT_LINK, "is_not": PROJECT_LINK, "type_is": "Project",
                 "type_is_not": "HumanUser", "name_contains": "fpt_parity",
                 "name_not_contains": _NONE, "name_is": "${project.name}",
                 "in": [PROJECT_LINK], "not_in": [PROJECT_LINK]}  # fmt: skip
    elif data_type in ("text", "list", "status_list", "checkbox"):
        value = parity_template(data_type)
        other = {"text": _NONE, "list": "fpt_b", "status_list": "ip", "checkbox": False}
        table = {"is": value, "is_not": other[data_type], "in": [value],
                 "not_in": [other[data_type]], "contains": "parity", "not_contains": _NONE,
                 "starts_with": "fpt", "ends_with": "parity"}  # fmt: skip
    elif data_type == "image":
        table = {"is": None, "is_not": None}
    else:
        table = {}
    if operator not in table:
        raise LookupError(f"no filter value for {data_type}.{operator}")
    return table[operator]


def filter_field(data_type: str, parity: set[str]) -> str | None:
    if data_type in parity:
        return fixtures.field_name(data_type)
    return "image" if data_type == "image" else None


def filter_op(
    data_type: str, operator: str, parity: set[str], multi_arg: Sequence[str]
) -> dict[str, Any] | None:
    field = filter_field(data_type, parity)
    if field is None:
        return None
    value = filter_value(data_type, operator)
    spread = operator in multi_arg and isinstance(value, list)
    condition = [field, operator, *value] if spread else [field, operator, value]
    shown = "Project:${project.id}" if value == PROJECT_LINK else text(value)
    scope, scope_argv = _project_filter()
    return _case(
        f"filter_op.{data_type}.{operator}",
        "find",
        "identical",
        {"entity_type": SHOT, "filters": [scope, condition], "fields": ["id"]},
        ["find", SHOT, *scope_argv, "-f", f"{field} {operator} {shown}", "--fields", "id"],
    )


# --- enum-value ------------------------------------------------------------------------------

NUMBER, CHECKBOX = fixtures.field_name("number"), fixtures.field_name("checkbox")
LIST, STATUS = fixtures.field_name("list"), fixtures.field_name("status_list")
# summary type -> the field it summarizes and, where the type needs one, its "value"
SUMMARY_FIELDS: dict[str, tuple[str, Any]] = {
    "record_count": ("id", None), "count": ("code", None), "sum": (NUMBER, None),
    "maximum": (NUMBER, None), "minimum": (NUMBER, None), "average": (NUMBER, None),
    "earliest": ("created_at", None), "latest": ("created_at", None),
    "percentage": (LIST, parity_template("list")),
    "status_percentage": (STATUS, parity_template("status_list")),
    "status_list": (STATUS, None), "checked": (CHECKBOX, None), "unchecked": (CHECKBOX, None),
}  # fmt: skip
# grouping type -> (entity type, field). entitytype needs a field that links to several types.
GROUP_FIELDS: dict[str, tuple[str, str]] = {
    "exact": (SHOT, "code"), "firstletter": (SHOT, "code"), "entitytype": (TASK, "entity"),
    **{name: (SHOT, NUMBER) for name in ("tens", "hundreds", "thousands", "tensofthousands",
                                         "hundredsofthousands", "millions")},
    **{name: (SHOT, "created_at") for name in ("day", "week", "month", "quarter", "year",
                                               "clustered_date")},
    "oneday": (SHOT, fixtures.field_name("duration")),
    "fivedays": (SHOT, fixtures.field_name("duration")),
}  # fmt: skip
_COUNT = [{"field": "id", "type": "record_count"}]


def _summarize(case_id: str, entity: str, summary: Any, grouping: Any = None) -> dict[str, Any]:
    scope, scope_argv = _project_filter()
    args: dict[str, Any] = {"entity_type": entity, "filters": [scope], "summary_fields": summary}
    argv = ["summarize", entity, *scope_argv, "--summary-fields", json.dumps(summary)]
    if grouping is not None:
        args["grouping"] = grouping
        argv += ["--grouping", json.dumps(grouping)]
    return _case(case_id, "summarize", "identical", args, argv)


def enum_cases(enum: str, values: Sequence[str]) -> dict[str, dict[str, Any]]:
    """value -> the case that uses it, for one enum."""
    cases: dict[str, dict[str, Any]] = {}
    if enum == "summary_type":
        for value in values:
            field, extra = SUMMARY_FIELDS[value]
            spec = {"field": field, "type": value, **({"value": extra} if extra else {})}
            cases[value] = _summarize(f"enum.summary_type.{value}", SHOT, [spec])
    elif enum == "grouping_type":
        for index, value in enumerate(values):
            entity, field = GROUP_FIELDS[value]
            direction = "asc" if index % 2 == 0 else "desc"
            grouping = [{"field": field, "type": value, "direction": direction}]
            cases[value] = _summarize(f"enum.grouping_type.{value}", entity, _COUNT, grouping)
    elif enum == "grouping_direction":
        for value in values:
            grouping = [{"field": "code", "type": "exact", "direction": value}]
            case_id = f"enum.grouping_direction.{value}"
            cases[value] = _summarize(case_id, SHOT, _COUNT, grouping)
    elif enum == "order_direction":
        scope, scope_argv = _project_filter()
        order = [{"field_name": "code", "direction": "asc"},
                 {"field_name": "id", "direction": "desc"}]  # fmt: skip
        case = _case(
            "enum.order_direction",
            "find",
            "identical",
            {"entity_type": SHOT, "filters": [scope], "fields": ["code"], "order": order},
            ["find", SHOT, *scope_argv, "--fields", "code", "--order", "code,-id"],
        )
        cases = {"asc": case, "desc": case}
    elif enum == "filter_operator":
        # A group is valid only as an element of the filter list (sandbox, 2026-11-10).
        raw = [{"filter_operator": "all", "filters": [_project_filter()[0]]}]
        cases["all"] = _case(
            "enum.filter_operator.all",
            "find",
            "identical",
            {"entity_type": SHOT, "filters": raw, "fields": ["id"]},
            ["find", SHOT, "--filters", text(raw), "--fields", "id"],
        )
        cases["any"] = _case(
            "enum.filter_operator.any",
            "find",
            "identical",
            {
                "entity_type": SHOT,
                "filters": [["id", "is", "${twin.id}"], ["id", "is", "${past.id}"]],
                "filter_operator": "any",
                "fields": ["id"],
            },
            ["find", SHOT, "-f", "id is ${twin.id}", "-f", "id is ${past.id}", "--any",
             "--fields", "id"],
        )  # fmt: skip
    return cases


# --- all of it -------------------------------------------------------------------------------


def generate(
    snapshot: Mapping[str, Any], dimensions: Mapping[str, Any], waived: set[str], cls: type
) -> dict[str, list[Entry]]:
    """file name -> (item, case) entries. Raises if a generated item has no case."""
    shot_fields = snapshot["fields"].get(SHOT, {})
    parity = {
        data_type
        for data_type in snapshot["data_types"]
        if shot_fields.get(fixtures.field_name(data_type)) == data_type
    }
    wanted = [
        item
        for item in compute_items(cls, snapshot["data_types"], dimensions)
        if item.split(":")[0] in GENERATED_KINDS and item not in waived | HAND_WRITTEN
    ]
    enums = {enum: enum_cases(enum, values) for enum, values in sorted(dimensions["enums"].items())}
    multi_arg = dimensions["multi_arg_operators"]["operators"]
    files: dict[str, list[Entry]] = {f"generated_{kind.replace('-', '_')}.json": []
                                     for kind in GENERATED_KINDS}  # fmt: skip
    missing = []
    for item in wanted:
        kind, _, rest = item.partition(":")
        case: dict[str, Any] | None
        if kind == "field-read":
            case = field_read(rest, parity)
        elif kind == "field-write":
            case = field_write(rest, parity)
        elif kind == "filter-op":
            data_type, _, operator = rest.partition(".")
            case = filter_op(data_type, operator, parity, multi_arg)
        else:
            enum, _, value = rest.partition(".")
            case = enums.get(enum, {}).get(value)
        if case is None:
            missing.append(item)
        else:
            files[f"generated_{kind.replace('-', '_')}.json"].append((item, case))
    if missing:
        raise LookupError(f"no generated case for: {', '.join(missing)}")
    return files


def render(entries: Sequence[Entry]) -> str:
    """One case per line, unique by id, sorted: the committed file's exact text."""
    unique = {case["id"]: case for _, case in entries}
    lines = [json.dumps(unique[case_id]) for case_id in sorted(unique)]
    return "[\n" + ",\n".join(lines) + "\n]\n"


def load_inputs() -> tuple[dict[str, Any], dict[str, Any], set[str], type]:
    import shotgun_api3

    snapshot = json.loads(LATEST.read_text(encoding="utf-8"))["schema"]
    dimensions = load_dimensions()
    cls = shotgun_api3.Shotgun
    items = compute_items(cls, snapshot["data_types"], dimensions)
    return snapshot, dimensions, set(load_waivers(WAIVERS_PATH, items)), cls


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(prog="python -m parity.generate", description=__doc__).parse_args(argv)
    if not LATEST.exists():
        print(f"parity.generate needs {LATEST}: run parity.runner first", file=sys.stderr)
        return 2
    for name, entries in generate(*load_inputs()).items():
        (CASES_DIR / name).write_text(render(entries), encoding="utf-8")
        print(f"{name}: {len({case['id'] for _, case in entries})} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
