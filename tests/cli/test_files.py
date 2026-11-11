import io
import sys
from datetime import datetime, timezone
from typing import Any

import pytest

SHOT = {"type": "Shot", "id": 1}
TASK = {"type": "Task", "id": 2}
WHEN = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
EXTRAS = ["--display-name", "d", "--tag-list", "t", "--created-at", "2026-01-02T03:04:05Z"]
EXTRA_ARGS = {"display_name": "d", "tag_list": "t", "created_at": WHEN}


def sent(harness: Any) -> list[tuple[str, dict[str, Any]]]:
    return [(name, kwargs) for name, _, kwargs in harness.client.calls]


def test_upload_with_every_option(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["upload"] = 941
    result = harness.run("upload", "Shot", "1", "a.png", "--field-name", "sg_file", *EXTRAS)
    assert (result.code, result.json) == (0, 941)
    harness.run("upload", "Shot", "1", "a.png")
    base = {"entity_type": "Shot", "entity_id": 1, "path": "a.png"}
    assert sent(harness) == [
        ("upload", {**base, "field_name": "sg_file", **EXTRA_ARGS}),
        ("upload", base),
    ]


@pytest.mark.parametrize(
    ("flags", "method"),
    [([], "upload_thumbnail"), (["--filmstrip"], "upload_filmstrip_thumbnail")],
)
def test_thumbnail_upload(harness: Any, flags: list[str], method: str) -> None:
    harness.use_script_env()
    harness.client.responses[method] = 8417
    result = harness.run("thumbnail", "upload", "Shot", "1", "a.png", *flags, *EXTRAS)
    assert (result.code, result.json) == (0, 8417)
    harness.run("thumbnail", "upload", "Shot", "1", "a.png", *flags)
    base = {"entity_type": "Shot", "entity_id": 1, "path": "a.png"}
    assert sent(harness) == [(method, {**base, **EXTRA_ARGS}), (method, base)]


def test_thumbnail_share(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["share_thumbnail"] = 5
    result = harness.run(
        "thumbnail", "share", "Shot:1", '{"type": "Task", "id": 2}', "--path", "f.png",
        "--filmstrip", *EXTRAS,
    )  # fmt: skip
    assert (result.code, result.json) == (0, 5)
    harness.run("thumbnail", "share", "Task:2", "--source", "Shot:1")
    assert sent(harness) == [
        (
            "share_thumbnail",
            {
                "entities": [SHOT, TASK],
                "thumbnail_path": "f.png",
                "filmstrip_thumbnail": True,
                **EXTRA_ARGS,
            },
        ),
        ("share_thumbnail", {"entities": [TASK], "source_entity": SHOT}),
    ]


@pytest.mark.parametrize(
    "argv",
    [
        ["thumbnail", "share", "Shot:1"],
        ["thumbnail", "share", "Shot:1", "--path", "f.png", "--source", "Shot:2"],
        ["thumbnail", "share", "--path", "f.png"],
        ["thumbnail", "share", "7", "--path", "f.png"],
        ["upload", "Shot", "x", "a.png"],
        ["upload", "Shot", "1", "a.png", "--created-at", "today"],
        ["download", "941"],
        ["download", "941", "-o", ""],
        ["download", '"text"', "-o", "-"],
        ["download", "true", "-o", "-"],
        ["download", "{nope", "-o", "-"],
        ["attachment", "url", "[1]"],
    ],
)
def test_file_usage_errors(harness: Any, argv: list[str]) -> None:
    harness.use_script_env()
    assert harness.run(*argv).code == 2
    assert harness.client.calls == []


def test_download_to_a_path_prints_the_path(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["download_attachment"] = "out.png"
    result = harness.run("download", "941", "-o", "out.png")
    assert (result.code, result.json) == (0, "out.png")
    assert sent(harness) == [("download_attachment", {"attachment": 941, "file_path": "out.png"})]


def test_download_to_stdout_writes_the_raw_bytes(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.use_script_env()
    data = b"\x89PNG\r\n\x1a\n\x00\xff"
    harness.client.responses["download_attachment"] = data
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(out, encoding="utf-8"))
    attachment = '{"url": "https://x/a.png", "type": "Attachment", "id": 941}'
    result = harness.run("download", attachment, "-o", "-")
    sys.stdout.flush()
    assert result.code == 0
    assert out.getvalue() == data
    assert sent(harness) == [
        (
            "download_attachment",
            {"attachment": {"url": "https://x/a.png", "type": "Attachment", "id": 941}},
        )
    ]


def test_attachment_url(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["get_attachment_download_url"] = "https://x/file_serve/attachment/941"
    result = harness.run("attachment", "url", "941")
    assert (result.code, result.json) == (0, "https://x/file_serve/attachment/941")
    assert sent(harness) == [("get_attachment_download_url", {"attachment": 941})]


@pytest.mark.parametrize(
    ("argv", "call", "args"),
    [
        (
            ["upload", "Shot", "1", "a.png"],
            "upload",
            {"entity_type": "Shot", "entity_id": 1, "path": "a.png", "field_name": None,
             "display_name": None, "tag_list": None, "created_at": None},
        ),
        (
            ["thumbnail", "upload", "Shot", "1", "a.png", "--display-name", "d"],
            "upload_thumbnail",
            {"entity_type": "Shot", "entity_id": 1, "path": "a.png", "display_name": "d"},
        ),
        (
            ["thumbnail", "upload", "Shot", "1", "a.png", "--filmstrip"],
            "upload_filmstrip_thumbnail",
            {"entity_type": "Shot", "entity_id": 1, "path": "a.png"},
        ),
        (
            ["thumbnail", "share", "Shot:1", "--source", "Shot:2"],
            "share_thumbnail",
            {"entities": [SHOT], "thumbnail_path": None, "source_entity": {"type": "Shot", "id": 2},
             "filmstrip_thumbnail": False},
        ),
    ],
)  # fmt: skip
def test_file_writes_dry_run(
    harness: Any, argv: list[str], call: str, args: dict[str, Any]
) -> None:
    result = harness.run(*argv, "--dry-run")
    assert (result.code, result.json) == (0, {"call": call, "args": args})
    assert harness.built == []
