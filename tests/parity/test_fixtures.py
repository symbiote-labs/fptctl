from datetime import date, datetime, timezone
from typing import Any

import pytest
from parity.fixtures import (
    EDITABLE_SANDBOX_TYPES,
    FIELD_ENTITY,
    Fixtures,
    ensure_fields,
    field_name,
    finish_run,
    run_dates,
    sample_value,
    scratch_field,
    start_run,
)

PROJECT = {"type": "Project", "id": 70, "name": "fpt_parity_x"}
LIST_SCHEMA = {"properties": {"valid_values": {"value": ["a", "b"]}}}
WHEN = datetime(2026, 12, 8, 12, 0)
LINKS = {"project": PROJECT, "dates": {"future": "2026-12-08", "future_time": WHEN}}
TODAY = date(2026, 11, 10)


class FakeSg:
    def __init__(self, existing: dict[str, Any] | None = None) -> None:
        self.fields: dict[str, Any] = dict(existing or {})
        self.calls: list[tuple[Any, ...]] = []
        self.refuse_create: set[str] = set()
        self.refuse_update: set[str] = set()
        self.refuse_delete: set[int] = set()
        self.leftovers: dict[str, list[dict[str, Any]]] = {}
        self.refuse_field_delete: set[str] = set()
        self.following: dict[int, list[dict[str, Any]]] = {}
        self.refuse_unfollow: set[int] = set()
        self.next_id = 100

    def schema_field_read(self, entity_type: str) -> dict[str, Any]:
        return dict(self.fields)

    def schema_field_create(
        self, entity_type: str, data_type: str, display_name: str, properties: Any = None
    ) -> str:
        self.calls.append(("schema_field_create", entity_type, data_type, display_name, properties))
        if data_type in self.refuse_create:
            raise RuntimeError(f"cannot create {data_type}")
        name = "sg_" + display_name.replace(" ", "_")
        self.fields[name] = {"data_type": {"value": data_type}, "properties": {}}
        return name

    def find_one(self, entity_type: str, filters: Any, fields: Any = None) -> Any:
        return {"type": "HumanUser", "id": 5, "name": "Ada"}

    def find(self, entity_type: str, filters: Any, fields: Any = None) -> list[dict[str, Any]]:
        self.calls.append(("find", entity_type, filters))
        return self.leftovers.get(entity_type, [])

    def create(self, entity_type: str, data: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create", entity_type, data))
        self.next_id += 1
        return {"type": entity_type, "id": self.next_id, **data}

    def update(self, entity_type: str, entity_id: int, data: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("update", entity_type, entity_id, data))
        if set(data) & self.refuse_update:
            raise RuntimeError("refused")
        return {"type": entity_type, "id": entity_id, **data}

    def user_subscriptions_read(self) -> dict[str, Any]:
        return {"5": "not_for_resale", "6": None}

    def activity_stream_read(self, entity_type: str, entity_id: int) -> dict[str, Any]:
        self.calls.append(("activity_stream_read", entity_type, entity_id))
        return {"updates": [{"id": 902}, {"id": 900}, {"id": 901}]}

    def followers(self, entity: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append(("followers", entity["id"]))
        return self.following.get(entity["id"], [])

    def unfollow(self, user: dict[str, Any], entity: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("unfollow", user["id"], entity["id"]))
        if entity["id"] in self.refuse_unfollow:
            raise RuntimeError("cannot unfollow")
        return {"unfollowed": True}

    def upload(self, entity_type: str, entity_id: int, path: str) -> int:
        self.calls.append(("upload", entity_type, entity_id, path))
        self.next_id += 1
        return self.next_id

    def schema_field_delete(self, entity_type: str, field_name: str) -> bool:
        self.calls.append(("schema_field_delete", entity_type, field_name))
        if field_name in self.refuse_field_delete:
            raise RuntimeError("cannot delete field")
        return True

    def delete(self, entity_type: str, entity_id: int) -> bool:
        self.calls.append(("delete", entity_type, entity_id))
        if entity_id in self.refuse_delete:
            raise RuntimeError("cannot delete")
        return True


def test_ensure_fields_creates_only_missing_and_records_refusals() -> None:
    sg = FakeSg({field_name("text"): {"data_type": {"value": "text"}}})
    sg.refuse_create = {"image"}
    report = ensure_fields(sg, ["text", "number", "entity", "image"])
    assert report.fields == {
        "text": "sg_fpt_parity_text",
        "number": "sg_fpt_parity_number",
        "entity": "sg_fpt_parity_entity",
    }
    assert report.created == ["sg_fpt_parity_entity", "sg_fpt_parity_number"]
    assert "cannot create image" in report.refused["image"]
    creates = [call for call in sg.calls if call[0] == "schema_field_create"]
    assert (
        "schema_field_create",
        FIELD_ENTITY,
        "entity",
        "fpt parity entity",
        {"valid_types": ["Project"]},
    ) in creates
    assert all(call[2] != "text" for call in creates)


def test_ensure_fields_stops_when_the_server_picks_another_code() -> None:
    sg = FakeSg()
    sg.schema_field_create = lambda *a, **k: "sg_something_else"  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="sg_something_else"):
        ensure_fields(sg, ["text"])


@pytest.mark.parametrize("data_type", sorted(EDITABLE_SANDBOX_TYPES - {"image"}))
def test_sample_values_are_not_empty(data_type: str) -> None:
    value = sample_value(data_type, LIST_SCHEMA, LINKS)
    assert value not in (None, "", [], {})


def test_sample_values_follow_the_field_schema_and_the_run() -> None:
    assert sample_value("list", LIST_SCHEMA, LINKS) == "a"
    assert sample_value("multi_entity", {}, LINKS) == [PROJECT]
    assert sample_value("date", {}, LINKS) == "2026-12-08"
    assert sample_value("date_time", {}, LINKS) == WHEN
    for unknown in ("image", "nonsense"):
        with pytest.raises(ValueError):
            sample_value(unknown, {}, LINKS)


@pytest.mark.parametrize(
    ("today", "month", "year"),
    [(date(2026, 11, 10), -1, 0), (date(2026, 1, 15), -1, -1), (date(2026, 3, 31), 0, 0)],
)
def test_run_dates_are_four_weeks_either_side(today: date, month: int, year: int) -> None:
    dates = run_dates(today)
    past = date.fromisoformat(dates["past"])
    assert (today - past).days == 28
    assert (date.fromisoformat(dates["future"]) - today).days == 28
    assert dates["future_time"] == dates["future"] + "T12:00:00Z"
    assert dates["past_time"] == dates["past"] + "T12:00:00Z"
    assert (dates["day"], dates["week"], dates["month"], dates["year"]) == (-28, -4, month, year)


def test_start_run_makes_identical_twins_for_each_role() -> None:
    sg = FakeSg()
    report = ensure_fields(sg, ["text", "number"])
    sg.refuse_update = {"sg_fpt_parity_number"}
    fixtures = start_run(sg, "RUN", report, "ada", TODAY)
    assert fixtures.project["name"] == "fpt_parity_RUN"
    assert fixtures.user == {"type": "HumanUser", "id": 5, "name": "Ada"}
    direct, cli = fixtures.for_side("direct"), fixtures.for_side("cli")
    for role in ("twin", "past", "victim", "task"):
        assert direct[role]["id"] != cli[role]["id"]
        assert {k: v for k, v in direct[role].items() if k != "id"} == {
            k: v for k, v in cli[role].items() if k != "id"
        }
    assert direct["dates"] == cli["dates"] == run_dates(TODAY)
    assert "refused" in fixtures.write_refused["number"]
    creates = [call[1:] for call in sg.calls if call[0] == "create"]
    assert ("Task", {"content": "fpt_parity_task", "project": fixtures.project,
                     "entity": cli["twin"]}) in creates  # fmt: skip
    assert len(creates) == 1 + 3 * 2 + 2 + 2
    note = {"type": "Note", "id": direct["note"]["id"]}
    assert (
        "Note",
        {
            "project": fixtures.project,
            "subject": "fpt parity",
            "content": "fpt parity note",
            "note_links": [direct["twin"]],
        },
    ) in creates
    assert ("Reply", {"entity": note, "content": "fpt parity reply"}) in creates  # fmt: skip
    assert direct["note"] == cli["note"] == note
    assert fixtures.reply is not None and fixtures.reply["type"] == "Reply"
    assert sg.calls[-1] == ("activity_stream_read", "Shot", direct["twin"]["id"])
    assert direct["activity"] == cli["activity"] == {"min_id": 900, "max_id": 902}
    uploads = [call for call in sg.calls if call[0] == "upload"]
    assert [call[1:3] for call in uploads] == [("Shot", direct["twin"]["id"])]
    assert uploads[0][3].endswith("parity/assets/fpt-parity.png")
    assert direct["attachment"] == cli["attachment"] == {"type": "Attachment", "id": sg.next_id - 2}
    assert direct["scratch"] == {
        "entity_type": "Asset",
        "display_name": "fpt parity scratch RUN",
        "field": "sg_fpt_parity_scratch_run",
    }
    assert cli["scratch"] == {**direct["scratch"], "entity_type": "Sequence"}
    text_updates = {
        call[2] for call in sg.calls if call[0] == "update" and "sg_fpt_parity_text" in call[3]
    }
    assert text_updates == {direct["twin"]["id"], cli["twin"]["id"]}
    task_updates = [call for call in sg.calls if call[0] == "update" and call[1] == "Task"]
    assert {call[2] for call in task_updates} == {direct["task"]["id"], cli["task"]["id"]}


def test_start_run_writes_future_dates_on_twins_and_past_dates_on_past() -> None:
    sg = FakeSg()
    fixtures = start_run(sg, "RUN", ensure_fields(sg, ["date", "date_time"]), None, TODAY)
    written = {
        (call[2], field): value
        for call in sg.calls
        if call[0] == "update"
        for field, value in call[3].items()
    }
    for side in ("direct", "cli"):
        twin, past = fixtures.twins[side]["id"], fixtures.past[side]["id"]
        assert written[(twin, "sg_fpt_parity_date")] == "2026-12-08"
        assert written[(past, "sg_fpt_parity_date")] == "2026-10-13"
        assert written[(twin, "sg_fpt_parity_date_time")] == datetime(
            2026, 12, 8, 12, 0, tzinfo=timezone.utc
        )
        assert written[(past, "sg_fpt_parity_date_time")] == datetime(
            2026, 10, 13, 12, 0, tzinfo=timezone.utc
        )


def test_start_run_reads_the_test_users_current_subscription() -> None:
    fixtures = start_run(FakeSg(), "RUN", ensure_fields(FakeSg(), []), "ada")
    assert fixtures.for_side("cli")["subscription"] == {
        "humanUserId": 5,
        "subscription": "not_for_resale",
    }
    assert start_run(FakeSg(), "RUN", ensure_fields(FakeSg(), []), None).subscription is None


def test_finish_run_retires_everything_and_keeps_going() -> None:
    sg = FakeSg()
    fixtures = Fixtures(
        project=PROJECT,
        user=None,
        twins={"direct": {"type": "Shot", "id": 1}, "cli": {"type": "Shot", "id": 2}},
        write_refused={},
        past={"direct": {"type": "Shot", "id": 3}, "cli": {"type": "Shot", "id": 4}},
        victims={"direct": {"type": "Shot", "id": 5}, "cli": {"type": "Shot", "id": 6}},
        tasks={"direct": {"type": "Task", "id": 7}, "cli": {"type": "Task", "id": 8}},
    )
    sg.refuse_delete = {9}
    sg.leftovers = {"Shot": [{"type": "Shot", "id": 11}]}
    failures = finish_run(sg, fixtures, [{"type": "Note", "id": 9}, {"type": "Note", "id": 10}])
    in_project = [["project", "is", {"type": "Project", "id": 70}]]
    assert [call for call in sg.calls] == [
        ("delete", "Note", 9),
        ("delete", "Note", 10),
        ("delete", "Task", 7),
        ("delete", "Task", 8),
        ("delete", "Shot", 5),
        ("delete", "Shot", 6),
        ("delete", "Shot", 3),
        ("delete", "Shot", 4),
        ("delete", "Shot", 1),
        ("delete", "Shot", 2),
        ("find", "Task", in_project),
        ("find", "Shot", in_project),
        ("delete", "Shot", 11),
        ("find", "Note", in_project),
        ("find", "WorkDayRule", in_project),
        ("delete", "Project", 70),
    ]
    assert len(failures) == 1 and "Note 9" in failures[0]


def test_finish_run_reports_a_failed_sweep_and_still_retires_the_project() -> None:
    sg = FakeSg()

    def find(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("down")

    sg.find = find  # type: ignore[method-assign]
    fixtures = Fixtures(project=PROJECT, user=None, twins={}, write_refused={})
    failures = finish_run(sg, fixtures, [])
    assert sg.calls == [("delete", "Project", 70)]
    assert [f.split(":")[0] for f in failures] == [
        "finding Tasks left in the run project",
        "finding Shots left in the run project",
        "finding Notes left in the run project",
        "finding WorkDayRules left in the run project",
    ]


def test_ensure_fields_sends_the_properties_each_type_requires() -> None:
    sg = FakeSg()
    ensure_fields(sg, ["checkbox", "list", "status_list", "multi_entity", "date"])
    sent = {call[2]: call[4] for call in sg.calls if call[0] == "schema_field_create"}
    assert sent == {
        "checkbox": {"default_value": False},
        "date": None,
        "list": {"valid_values": ["fpt_a", "fpt_b"]},
        "multi_entity": {"valid_types": ["Project"]},
        "status_list": {"valid_values": ["wtg", "ip"]},
    }


def test_start_run_retires_what_it_made_when_setup_fails() -> None:
    sg = FakeSg()
    real_create = sg.create
    made: list[int] = []

    def create(entity_type: str, data: dict[str, Any]) -> dict[str, Any]:
        if len(made) == 1:
            raise RuntimeError("Project Name field is required to be unique")
        result = real_create(entity_type, data)
        made.append(result["id"])
        return result

    sg.create = create  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="unique"):
        start_run(sg, "RUN", ensure_fields(FakeSg(), []), "ada")
    assert ("delete", "Project", made[0]) in sg.calls


@pytest.mark.parametrize(
    ("run_id", "field"),
    [
        ("20261111T000400Z", "sg_fpt_parity_scratch_20261111t000400z"),
        ("a-b", "sg_fpt_parity_scratch_a_b"),
    ],
)
def test_scratch_field_name_follows_the_display_name(run_id: str, field: str) -> None:
    assert scratch_field(run_id) == field


def test_finish_run_deletes_only_this_runs_scratch_fields() -> None:
    sg = FakeSg()
    sg.fields = {
        "code": {},
        "sg_fpt_parity_scratch_run": {},
        "sg_fpt_parity_scratch_run_1": {},
        "sg_fpt_parity_scratch_run_x": {},
        "sg_fpt_parity_scratch_other": {},
        "sg_fpt_parity_scratchpad": {},
        "sg_fpt_parity_text": {},
    }
    sg.refuse_field_delete = {"sg_fpt_parity_scratch_run_1"}
    fixtures = Fixtures(
        project=PROJECT, user=None, twins={}, write_refused={},
        attachment={"type": "Attachment", "id": 40}, run_id="RUN",
    )  # fmt: skip
    failures = finish_run(sg, fixtures, [])
    assert ("delete", "Attachment", 40) in sg.calls
    field_deletes = [call[1:] for call in sg.calls if call[0] == "schema_field_delete"]
    assert field_deletes == [
        ("Asset", "sg_fpt_parity_scratch_run"),
        ("Asset", "sg_fpt_parity_scratch_run_1"),
        ("Sequence", "sg_fpt_parity_scratch_run"),
        ("Sequence", "sg_fpt_parity_scratch_run_1"),
    ]
    assert sg.calls[-1] == ("delete", "Project", 70)
    assert len(failures) == 2 and all("sg_fpt_parity_scratch_run_1" in f for f in failures)


def test_finish_run_without_a_run_id_deletes_no_fields() -> None:
    sg = FakeSg()
    sg.fields = {"sg_fpt_parity_scratch": {}, "sg_fpt_parity_scratch_1": {}}
    finish_run(sg, Fixtures(project=PROJECT, user=None, twins={}, write_refused={}), [])
    assert not [call for call in sg.calls if call[0] == "schema_field_delete"]


def test_start_run_records_no_activity_bounds_for_an_empty_stream() -> None:
    sg = FakeSg()
    sg.activity_stream_read = lambda *args: {"updates": []}  # type: ignore[method-assign]
    assert start_run(sg, "RUN", ensure_fields(FakeSg(), []), None).activity == {}


def test_finish_run_unfollows_and_retires_the_note_and_the_users_rule() -> None:
    sg = FakeSg()
    user = {"type": "HumanUser", "id": 5, "name": "Ada"}
    fixtures = Fixtures(
        project=PROJECT,
        user=user,
        twins={"direct": {"type": "Shot", "id": 1}, "cli": {"type": "Shot", "id": 2}},
        write_refused={},
        note={"type": "Note", "id": 20},
        reply={"type": "Reply", "id": 21},
        run_id="RUN",
    )
    rule_filter = [
        ["user", "is", {"type": "HumanUser", "id": 5}],
        ["start_date", "is", "2099-01-05"],
        ["description", "is", "fpt parity RUN"],
    ]
    real_find = sg.find

    def find(entity_type: str, filters: Any, fields: Any = None) -> list[dict[str, Any]]:
        real_find(entity_type, filters, fields)
        if entity_type == "WorkDayRule":
            rule_id = 31 if filters == rule_filter else 30
            return [{"type": "WorkDayRule", "id": rule_id}]
        return []

    sg.find = find  # type: ignore[method-assign]
    sg.following = {1: [{"type": "HumanUser", "id": 5}], 2: [{"type": "HumanUser", "id": 6}]}
    sg.refuse_unfollow = {1}
    failures = finish_run(sg, fixtures, [])
    calls = sg.calls
    assert calls[:4] == [("followers", 1), ("unfollow", 5, 1), ("followers", 2),
                         ("delete", "Reply", 21)]  # fmt: skip
    assert calls.index(("delete", "Reply", 21)) < calls.index(("delete", "Note", 20))
    assert ("find", "WorkDayRule", rule_filter) in calls
    assert ("delete", "WorkDayRule", 30) in calls  # the run project's rule
    assert ("delete", "WorkDayRule", 31) in calls  # this run's rule for the test user
    assert calls[-1] == ("delete", "Project", 70)
    assert len(failures) == 1 and "unfollow" in failures[0]
