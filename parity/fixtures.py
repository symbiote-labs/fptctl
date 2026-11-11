"""Sandbox test data (spec, "Fixtures").

Long-lived custom fields `sg_fpt_parity_<data type>` on Shot, created once and reused. Each run
creates a project `fpt_parity_<run id>` and, in it, one pair of identical twins (one per side) for
each role, and retires all of them at the end:

- twin: a Shot with every parity field set; date fields hold the run's future date;
- past: a Shot whose date fields hold the run's past date, so past-relative filters can match;
- victim: a bare Shot for delete, revive and batch to act on;
- task: a Task on the twin Shot with color, dates and splits set.

Also per run: one Attachment (the parity PNG uploaded to the direct twin) for the download cases,
and a scratch-field slot per side for the schema write cases. The scratch field's display name
carries the run id, because a deleted field goes to the Trash and keeps its name blocked; each side
uses its own entity type, so both sides create a field of the same name.

Also per run, for the activity and note cases: a Note in the run project on the direct twin, with
one Reply, and bounds on the direct twin's activity stream, read once setup is done, so a
max_id read stays the same while later cases add events. finish_run also unfollows the twins
for the test user, deletes the run project's work-day rules, and deletes the test user's
2099-01-05 rule that the `work_schedule_update.user` case writes (its description carries the
run id, so only this run's rule matches).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

FIELD_ENTITY = "Shot"
FIELD_PREFIX = "sg_fpt_parity_"
PROJECT_PREFIX = "fpt_parity_"
TWIN_NAME = "fpt_parity_twin"
PAST_NAME = "fpt_parity_past"
VICTIM_NAME = "fpt_parity_victim"
TASK_NAME = "fpt_parity_task"
TASK_ENTITY = "Task"
NOTE_ENTITY = "Note"
REPLY_ENTITY = "Reply"
RULE_ENTITY = "WorkDayRule"
PARITY_TEXT = "fpt parity"
# The date of the test user's work-day rule in the work_schedule_update.user case.
USER_RULE_DATE = "2099-01-05"
# Fixed values on the Task twins. splits must fall between start_date and due_date.
TASK_VALUES: dict[str, Any] = {
    "color": "255,0,0",
    "start_date": "2026-11-09",
    "due_date": "2026-11-13",
    "splits": [
        {"start": "2026-11-09", "end": "2026-11-10"},
        {"start": "2026-11-12", "end": "2026-11-13"},
    ],
}
# The run's dates are this many days (exactly four weeks) from the run day, so the calendar
# offset in weeks does not depend on the day a week starts.
DATE_SPAN = 28
DATE_TYPES = ("date", "date_time")
SIDES = ("direct", "cli")
IMAGE_ASSET = Path(__file__).resolve().parent / "assets" / "fpt-parity.png"
SCRATCH_TYPES = {"direct": "Asset", "cli": "Sequence"}
SCRATCH_DISPLAY = "fpt parity scratch"
# Editable data types on the sandbox when Phase 2 was planned (2026-11-10).
EDITABLE_SANDBOX_TYPES = frozenset(
    {
        "checkbox", "color", "date", "date_time", "duration", "entity", "entity_type", "float",
        "image", "list", "multi_entity", "number", "password", "percent", "serializable",
        "status_list", "text", "url",
    }
)  # fmt: skip
# Properties the server requires when creating a field of these types (sandbox, 2026-11-10).
# status_list values must be existing Status codes; wtg and ip exist on the sandbox.
_CREATE_PROPERTIES: dict[str, dict[str, Any]] = {
    "checkbox": {"default_value": False},
    "entity": {"valid_types": ["Project"]},
    "list": {"valid_values": ["fpt_a", "fpt_b"]},
    "multi_entity": {"valid_types": ["Project"]},
    "status_list": {"valid_values": ["wtg", "ip"]},
}


def field_name(data_type: str) -> str:
    return FIELD_PREFIX + data_type


@dataclass(frozen=True)
class FieldReport:
    fields: dict[str, str] = field(default_factory=dict)  # data type -> field name
    created: list[str] = field(default_factory=list)
    refused: dict[str, str] = field(default_factory=dict)  # data type -> server message


def run_dates(today: date) -> dict[str, Any]:
    """The run's future and past dates, in wire form, and the past date's calendar offsets."""
    future, past = today + timedelta(days=DATE_SPAN), today - timedelta(days=DATE_SPAN)
    return {
        "future": future.isoformat(),
        "past": past.isoformat(),
        "future_time": f"{future.isoformat()}T12:00:00Z",
        "past_time": f"{past.isoformat()}T12:00:00Z",
        "day": -DATE_SPAN,
        "week": -DATE_SPAN // 7,
        "month": (past.year - today.year) * 12 + past.month - today.month,
        "year": past.year - today.year,
    }


def _datetime(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Fixtures:
    project: dict[str, Any]
    user: dict[str, Any] | None
    twins: dict[str, dict[str, Any]]  # side -> Shot link
    write_refused: dict[str, str]  # data type -> server message
    # The test user's current entry from user_subscriptions_read, for the re-send case.
    subscription: dict[str, Any] | None = None
    past: dict[str, dict[str, Any]] = field(default_factory=dict)  # side -> Shot link
    victims: dict[str, dict[str, Any]] = field(default_factory=dict)  # side -> Shot link
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)  # side -> Task link
    dates: dict[str, Any] = field(default_factory=dict)  # run_dates()
    attachment: dict[str, Any] | None = None  # the uploaded parity PNG
    run_id: str = ""
    note: dict[str, Any] | None = None  # on the direct twin, with one Reply
    reply: dict[str, Any] | None = None
    activity: dict[str, Any] = field(default_factory=dict)  # {"min_id", "max_id"}, direct twin

    def for_side(self, side: str) -> dict[str, Any]:
        return {
            "project": self.project,
            "user": self.user,
            "twin": self.twins[side],
            "past": self.past.get(side),
            "victim": self.victims.get(side),
            "task": self.tasks.get(side),
            "dates": self.dates,
            "subscription": self.subscription,
            "attachment": self.attachment,
            "note": self.note,
            "activity": self.activity,
            "run_id": self.run_id,
            "scratch": {
                "entity_type": SCRATCH_TYPES[side],
                "display_name": f"{SCRATCH_DISPLAY} {self.run_id}",
                "field": scratch_field(self.run_id),
            },
        }


def scratch_field(run_id: str) -> str:
    """The field name the server derives from the scratch display name (sandbox, 2026-11-11)."""
    return "sg_" + re.sub(r"[^a-z0-9]+", "_", f"{SCRATCH_DISPLAY} {run_id}".lower()).strip("_")


def _error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def ensure_fields(sg: Any, data_types: Iterable[str]) -> FieldReport:
    """Create each missing parity field. Existing fields are reused and never altered."""
    existing = sg.schema_field_read(FIELD_ENTITY)
    report = FieldReport()
    for data_type in sorted(data_types):
        name = field_name(data_type)
        if name in existing:
            report.fields[data_type] = name
            continue
        properties = _CREATE_PROPERTIES.get(data_type)
        try:
            created = sg.schema_field_create(
                FIELD_ENTITY, data_type, f"fpt parity {data_type}", properties
            )
        except Exception as exc:  # the server's refusal is classification evidence
            report.refused[data_type] = _error(exc)
            continue
        if created != name:
            raise RuntimeError(
                f"The server named the {data_type} parity field {created}, not {name}. "
                "Stop and report; do not rename it."
            )
        report.fields[data_type] = name
        report.created.append(name)
    return report


def sample_value(data_type: str, field_schema: Mapping[str, Any], links: Mapping[str, Any]) -> Any:
    """One deterministic, non-empty value of `data_type`, valid for the field it is written to.

    `links` gives the run's values: "project" (a link) and "dates" (the "future" date and the
    "future_time" date_time).
    """
    valid = field_schema.get("properties", {}).get("valid_values", {}).get("value") or []
    fixed: dict[str, Any] = {
        "checkbox": True,
        "color": "255,0,0",
        "duration": 90,
        "entity_type": "Shot",
        "float": 1.5,
        "number": 7,
        "password": "fpt-parity",
        "percent": 50,
        "serializable": {"fpt": "parity"},
        "text": "fpt parity",
        "url": {"url": "https://example.com/fpt-parity", "name": "fpt parity"},
    }
    if data_type in fixed:
        return fixed[data_type]
    if data_type in ("list", "status_list") and valid:
        return valid[0]
    if data_type == "date":
        return links["dates"]["future"]
    if data_type == "date_time":
        return links["dates"]["future_time"]
    if data_type == "entity":
        return links["project"]
    if data_type == "multi_entity":
        return [links["project"]]
    raise ValueError(f"No sample value for data type {data_type!r}")


def start_run(
    sg: Any,
    run_id: str,
    fields: FieldReport,
    human_login: str | None,
    today: date | None = None,
) -> Fixtures:
    """Create the run's fixtures. If setup fails partway, retire what it made, then re-raise."""
    made: list[dict[str, Any]] = []
    dates = run_dates(today or datetime.now(timezone.utc).date())
    try:
        return _build_run(sg, run_id, fields, human_login, dates, made)
    except Exception:
        for target in reversed(made):
            try:
                sg.delete(target["type"], target["id"])
            except Exception as exc:  # report and keep retiring the rest
                print(
                    f"could not retire {target['type']} {target['id']}: {_error(exc)}",
                    file=sys.stderr,
                )
        raise


def _build_run(
    sg: Any,
    run_id: str,
    fields: FieldReport,
    human_login: str | None,
    dates: dict[str, Any],
    made: list[dict[str, Any]],
) -> Fixtures:
    def create(entity_type: str, data: dict[str, Any]) -> Any:
        result = sg.create(entity_type, data)
        made.append({"type": entity_type, "id": result["id"]})
        return result

    def link(entity_type: str, name_field: str, name: str, data: dict[str, Any]) -> dict[str, Any]:
        made_id = create(entity_type, {name_field: name, **data})["id"]
        return {"type": entity_type, "id": made_id, "name": name}

    def pair(entity_type: str, name_field: str, name: str, data: dict[str, Any]) -> dict[str, Any]:
        """One identical entity per side."""
        return {side: link(entity_type, name_field, name, data) for side in SIDES}

    name = PROJECT_PREFIX + run_id
    project = create("Project", {"name": name})
    project_link = {"type": "Project", "id": project["id"], "name": name}
    user = None
    subscription = None
    if human_login:
        found = sg.find_one("HumanUser", [["login", "is", human_login]], ["name"])
        user = {"type": "HumanUser", "id": found["id"], "name": found["name"]} if found else None
    if user is not None:
        current = sg.user_subscriptions_read()
        if str(user["id"]) in current:
            subscription = {"humanUserId": user["id"], "subscription": current[str(user["id"])]}
    in_project = {"project": project_link}
    twins = pair(FIELD_ENTITY, "code", TWIN_NAME, in_project)
    past = pair(FIELD_ENTITY, "code", PAST_NAME, in_project)
    victims = pair(FIELD_ENTITY, "code", VICTIM_NAME, in_project)
    tasks = {
        side: link(TASK_ENTITY, "content", TASK_NAME, {**in_project, "entity": twins[side]})
        for side in SIDES
    }
    schema = sg.schema_field_read(FIELD_ENTITY)
    links = {
        "project": project_link,
        "dates": {"future": dates["future"], "future_time": _datetime(dates["future_time"])},
    }
    past_values = {"date": dates["past"], "date_time": _datetime(dates["past_time"])}
    refused: dict[str, str] = {}
    for data_type, field_code in sorted(fields.fields.items()):
        try:
            value = sample_value(data_type, schema.get(field_code, {}), links)
            for side in SIDES:
                sg.update(FIELD_ENTITY, twins[side]["id"], {field_code: value})
                if data_type in DATE_TYPES:
                    sg.update(FIELD_ENTITY, past[side]["id"], {field_code: past_values[data_type]})
        except Exception as exc:  # recorded as field-write classification evidence
            refused[data_type] = _error(exc)
    for task in tasks.values():
        sg.update(TASK_ENTITY, task["id"], TASK_VALUES)
    attachment = {
        "type": "Attachment",
        "id": sg.upload(FIELD_ENTITY, twins["direct"]["id"], str(IMAGE_ASSET)),
    }
    made.append(attachment)
    note = {"type": NOTE_ENTITY, "id": create(NOTE_ENTITY, {
        **in_project, "subject": PARITY_TEXT, "content": f"{PARITY_TEXT} note",
        "note_links": [twins["direct"]],
    })["id"]}  # fmt: skip
    reply_id = create(REPLY_ENTITY, {"entity": note, "content": f"{PARITY_TEXT} reply"})["id"]
    # Last, so max_id covers every setup event and a max_id read ignores what later cases add.
    # The server refuses min_id with max_id, so each activity case uses one of them (sandbox,
    # 2026-11-11).
    stream = sg.activity_stream_read(FIELD_ENTITY, twins["direct"]["id"])
    update_ids = [update["id"] for update in stream["updates"]]
    activity = {"min_id": min(update_ids), "max_id": max(update_ids)} if update_ids else {}
    return Fixtures(
        project=project_link,
        user=user,
        twins=twins,
        write_refused=refused,
        subscription=subscription,
        past=past,
        victims=victims,
        tasks=tasks,
        dates=dates,
        attachment=attachment,
        run_id=run_id,
        note=note,
        reply={"type": REPLY_ENTITY, "id": reply_id},
        activity=activity,
    )


def finish_run(sg: Any, fixtures: Fixtures, created: Sequence[Mapping[str, Any]]) -> list[str]:
    """Retire what the run made. Never raises: one failure must not strand the rest.

    First it unfollows the twins for the test user. After the tracked entities, it retires every
    Task, Shot, Note and work-day rule still live in the run project, which catches what a case
    made without returning a link (a batch create, for one), and the test user's parity rule.
    Then it deletes this run's scratch field on the scratch entity types if it is still live,
    which catches a run that stopped between the field-create and field-delete cases. Other runs'
    fields are left alone.
    """
    failures = []
    if fixtures.user is not None:
        for twin in (fixtures.twins[side] for side in SIDES if side in fixtures.twins):
            try:
                if any(f["id"] == fixtures.user["id"] for f in sg.followers(twin)):
                    sg.unfollow(fixtures.user, twin)
            except Exception as exc:
                failures.append(f"unfollow {twin['type']} {twin['id']}: {_error(exc)}")
    targets: list[Mapping[str, Any]] = [*created]
    for made in (fixtures.attachment, fixtures.reply, fixtures.note):
        if made is not None:
            targets.append(made)
    for role in (fixtures.tasks, fixtures.victims, fixtures.past, fixtures.twins):
        targets += [role[side] for side in SIDES if side in role]

    def retire(target: Mapping[str, Any]) -> None:
        try:
            sg.delete(target["type"], target["id"])
        except Exception as exc:
            failures.append(f"{target['type']} {target['id']}: {_error(exc)}")

    for target in targets:
        retire(target)
    project_filter = [["project", "is", {"type": "Project", "id": fixtures.project["id"]}]]
    for entity_type in (TASK_ENTITY, FIELD_ENTITY, NOTE_ENTITY, RULE_ENTITY):
        try:
            leftovers = sg.find(entity_type, project_filter, ["id"])
        except Exception as exc:
            failures.append(f"finding {entity_type}s left in the run project: {_error(exc)}")
            continue
        for leftover in leftovers:
            retire(leftover)
    if fixtures.user is not None and fixtures.run_id:
        # Only this run's rule: the description carries the run id.
        user = {"type": "HumanUser", "id": fixtures.user["id"]}
        rule_filter = [
            ["user", "is", user],
            ["start_date", "is", USER_RULE_DATE],
            ["description", "is", f"{PARITY_TEXT} {fixtures.run_id}"],
        ]
        try:
            rules = sg.find(RULE_ENTITY, rule_filter, ["id"])
        except Exception as exc:
            failures.append(f"finding the test user's parity work-day rule: {_error(exc)}")
            rules = []
        for rule in rules:
            retire(rule)
    # Only this run's scratch field, or a name the server suffixed (_1, _2...) on a clash.
    ours = re.compile(re.escape(scratch_field(fixtures.run_id)) + r"(_\d+)?")
    for entity_type in SCRATCH_TYPES.values() if fixtures.run_id else ():
        try:
            names = sorted(sg.schema_field_read(entity_type))
        except Exception as exc:
            failures.append(f"reading {entity_type} fields: {_error(exc)}")
            continue
        for name in names:
            if ours.fullmatch(name):
                try:
                    sg.schema_field_delete(entity_type, name)
                except Exception as exc:
                    failures.append(f"{entity_type}.{name}: {_error(exc)}")
    retire(fixtures.project)
    return failures
