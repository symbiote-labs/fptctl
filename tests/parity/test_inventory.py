from typing import Any

from parity.inventory import compute_items, covered_items

DIMENSIONS: dict[str, Any] = {
    "surfaces": {"find": "find", "create": "create", "summarize": "summarize"},
    "not_exposed": {"find.legacy": "deprecated"},
    "filter_operators": {"text": ["is", "contains"], "number": ["between"], "absent": ["is"]},
    "enums": {"summary_type": ["record_count", "sum"], "order_direction": ["asc", "desc"]},
    "enum_params": {
        "summarize.summary_fields[].type": "summary_type",
        "find.order[].direction": "order_direction",
    },
}
SCHEMA = {"Shot": {"code": "text", "sg_cut_in": "number", "created_by": "entity"}}


class Lib:
    server_info: dict[str, Any] = {}

    def __init__(self, base_url: str, api_key: str | None = None, connect: bool = True) -> None: ...
    def find(
        self,
        entity_type: str,
        filters: Any,
        fields: Any = None,
        order: Any = None,
        limit: int = 0,
        legacy: Any = None,
    ) -> Any: ...
    def create(self, entity_type: str, data: Any, return_fields: Any = None) -> Any: ...
    def summarize(self, entity_type: str, filters: Any, summary_fields: Any) -> Any: ...
    def preferences_read(self, prefs: Any = None) -> Any: ...
    def upload_thumbnail(
        self, entity_type: str, entity_id: int, path: str, **kwargs: Any
    ) -> Any: ...
    def _hidden(self) -> None: ...


def find_trace(**args: Any) -> list[dict[str, Any]]:
    full = {
        "entity_type": "Shot",
        "filters": [],
        "fields": None,
        "order": None,
        "limit": 0,
        "legacy": None,
        **args,
    }
    return [
        {"construct": {"base_url": "https://x", "api_key": "<redacted>", "connect": False}},
        {"call": "find", "args": full},
    ]


def covered(
    argv: list[str], trace: list[dict[str, Any]], direct: Any = None, mode: str = "identical"
) -> set[str]:
    return covered_items(
        argv=argv,
        trace=trace,
        direct=direct,
        mode=mode,
        schema_fields=SCHEMA,
        dimensions=DIMENSIONS,
        cls=Lib,
    )


def test_compute_items() -> None:
    items = compute_items(Lib, {"text": True, "number": True, "summary": False}, DIMENSIONS)
    assert "method:find" in items and "method:_hidden" not in items
    assert "method:server_info" not in items
    assert "param:find.limit" in items and "param:Shotgun.connect" in items
    assert "param:upload_thumbnail.path" in items
    assert "param:upload_thumbnail.kwargs" in items
    assert not any(".self" in item for item in items)
    assert {"field-read:summary", "field-write:text"} <= set(items)
    assert "field-write:summary" not in items
    assert {"filter-op:text.contains", "filter-op:number.between"} <= set(items)
    assert "filter-op:absent.is" not in items
    assert "enum-value:summary_type.sum" in items
    assert items == sorted(items)


def test_method_and_params_need_the_designed_surface() -> None:
    on_surface = covered(["find", "Shot", "--limit", "5"], find_trace(limit=5))
    assert {
        "method:find",
        "param:find.entity_type",
        "param:find.filters",
        "param:find.limit",
    } <= on_surface
    assert "param:find.fields" not in on_surface
    via_api = covered(["api", "call", "find"], find_trace(limit=5))
    assert "method:find" not in via_api and "param:find.limit" not in via_api


def test_kwargs_param_counts_when_an_extra_keyword_is_traced() -> None:
    DIMENSIONS["surfaces"]["upload_thumbnail"] = "thumbnail upload"
    base = {"entity_type": "Shot", "entity_id": 1, "path": "/a.png"}
    argv = ["thumbnail", "upload", "Shot", "1", "/a.png"]
    plain = covered(argv, [{"call": "upload_thumbnail", "args": base}])
    extra = covered(argv, [{"call": "upload_thumbnail", "args": {**base, "tag_list": "x"}}])
    assert "param:upload_thumbnail.kwargs" not in plain
    assert "param:upload_thumbnail.kwargs" in extra
    del DIMENSIONS["surfaces"]["upload_thumbnail"]


def test_not_exposed_params_count_through_api_call() -> None:
    assert "param:find.legacy" in covered(["api", "call", "find"], find_trace(legacy=1))


def test_api_only_methods_count_through_api_call() -> None:
    trace = [{"call": "preferences_read", "args": {"prefs": ["x"]}}]
    assert {"method:preferences_read", "param:preferences_read.prefs"} <= covered(
        ["api", "call", "preferences_read"], trace
    )


def test_constructor_params_come_from_the_construct_line() -> None:
    found = covered(["find", "Shot"], find_trace())
    assert {"param:Shotgun.base_url", "param:Shotgun.api_key", "param:Shotgun.connect"} <= found


def test_field_read_from_identical_results_only() -> None:
    rows = [{"type": "Shot", "id": 1, "code": "sh010", "sg_cut_in": None, "created_by": []}]
    assert "field-read:text" in covered(["find", "Shot"], find_trace(), rows)
    assert not {"field-read:number", "field-read:entity"} & covered(
        ["find", "Shot"], find_trace(), rows
    )
    assert "field-read:text" not in covered(["find", "Shot"], find_trace(), rows, mode="mirrored")


def test_field_write_from_traced_data() -> None:
    trace = [
        {
            "call": "create",
            "args": {"entity_type": "Shot", "data": {"code": "x"}, "return_fields": None},
        }
    ]
    assert "field-write:text" in covered(["create", "Shot"], trace, mode="mirrored")


def test_filter_ops_need_shorthand() -> None:
    filters = [
        ["code", "contains", "sh"],
        {"filter_operator": "any", "filters": [["sg_cut_in", "between", 1, 5]]},
    ]
    trace = find_trace(filters=filters)
    assert {"filter-op:text.contains", "filter-op:number.between"} <= covered(
        ["find", "Shot", "-f", "x"], trace
    )
    assert not any(
        i.startswith("filter-op:") for i in covered(["find", "Shot", "--filters", "[]"], trace)
    )


def test_enum_values_from_traced_paths() -> None:
    assert "enum-value:order_direction.desc" in covered(
        ["find", "Shot"], find_trace(order=[{"field_name": "code", "direction": "desc"}])
    )


def test_real_dimensions_name_real_methods() -> None:
    import shotgun_api3
    from parity.inventory import load_dimensions, public_methods

    dimensions = load_dimensions()
    methods = set(public_methods(shotgun_api3.Shotgun))
    named = set(dimensions["surfaces"])
    named |= {key.split(".")[0] for key in dimensions["not_exposed"]}
    named |= {key.split(".")[0] for key in dimensions["enum_params"]}
    assert named <= methods
    for key in dimensions["not_exposed"]:
        method, parameter = key.split(".")
        assert parameter in public_methods(shotgun_api3.Shotgun)[method].parameters
    assert set(dimensions["enum_params"].values()) <= set(dimensions["enums"])
    assert all(dimensions["enums"].values())
