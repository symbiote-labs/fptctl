"""Ratchets: every command documents itself completely, and the skill matches the source.

A failure here names the command and says what is missing. Fix the command's docstring in
src/fpt/commands/, then run `uv run python -m scripts.skill_docs`.
"""

import re
import shlex
from pathlib import Path

import click
import pytest
from scripts import skill_docs

from fpt.cli import cli

DOCS = skill_docs.command_docs()
SHELL_OPERATORS = {"|", "||", "&&", ";", "<", ">", ">>", "&"}


def example_argv(example: str) -> list[str]:
    """The arguments after `fpt` in the one shell segment of an example that runs fpt."""
    lexer = shlex.shlex(example, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    segments: list[list[str]] = [[]]
    for token in lexer:
        if token in SHELL_OPERATORS:
            segments.append([])
        else:
            segments[-1].append(token)
    runs = [segment for segment in segments if segment[:1] == ["fpt"]]
    assert len(runs) == 1, f"example must run fpt exactly once: {example!r}"
    return runs[0][1:]


def parse_without_running(argv: list[str]) -> click.Command:
    """Parse argv against the real CLI (types, required arguments, unknown flags), call nothing."""
    context = cli.make_context("fpt", list(argv))
    command: click.Command = cli
    rest = [*getattr(context, "_protected_args", []), *context.args]
    while isinstance(command, click.Group):
        name, sub, rest = command.resolve_command(context, rest)
        assert sub is not None and name is not None
        context = sub.make_context(name, rest, parent=context)
        command = sub
        rest = [*getattr(context, "_protected_args", []), *context.args]
    return command


@pytest.mark.parametrize("doc", DOCS, ids=lambda doc: doc.name)
def test_command_has_summary_description_and_examples(doc: skill_docs.CommandDoc) -> None:
    assert doc.summary.endswith("."), f"{doc.name}: the first docstring line is the summary"
    assert len(doc.body.split()) >= 8, f"{doc.name}: add a description after the summary"
    assert doc.examples, f"{doc.name}: add an `Examples:` block with at least one example"


@pytest.mark.parametrize("doc", DOCS, ids=lambda doc: doc.name)
def test_command_description_explains_every_argument(doc: skill_docs.CommandDoc) -> None:
    context = click.Context(doc.command)
    text = f"{doc.summary}\n{doc.body}"
    for param in doc.command.params:
        if isinstance(param, click.Argument):
            name = re.sub(r"[\[\].]", "", param.make_metavar(context))
            assert re.search(rf"\b{re.escape(name)}\b", text), (
                f"{doc.name}: the docstring never mentions its argument {name}"
            )


@pytest.mark.parametrize("doc", DOCS, ids=lambda doc: doc.name)
def test_command_options_all_have_help(doc: skill_docs.CommandDoc) -> None:
    missing = [
        param.opts[0]
        for param in doc.command.params
        if isinstance(param, click.Option) and not param.help and param.name != "help"
    ]
    assert not missing, f"{doc.name}: options with no help text: {missing}"


EXAMPLES = [(doc, example) for doc in DOCS for example in doc.examples]


@pytest.mark.parametrize(
    ("doc", "example"), EXAMPLES, ids=[f"{doc.name}: {example}" for doc, example in EXAMPLES]
)
def test_example_parses_and_runs_its_own_command(doc: skill_docs.CommandDoc, example: str) -> None:
    command = parse_without_running(example_argv(example))
    assert command is doc.command, f"{doc.name}: example runs another command: {example!r}"


def test_group_and_root_help_is_present() -> None:
    def groups(group: click.Group) -> list[click.Group]:
        found = [group]
        for sub in group.commands.values():
            if isinstance(sub, click.Group):
                found += groups(sub)
        return found

    missing = [group.name for group in groups(cli) if not (group.help or "").strip()]
    assert not missing, f"command groups with no docstring: {missing}"


def test_skill_docs_match_the_cli_source() -> None:
    stale = [str(path.relative_to(skill_docs.ROOT)) for path in skill_docs.stale_files()]
    assert not stale, f"stale skill docs {stale}; run: uv run python -m scripts.skill_docs"


SKILL_ROOT = skill_docs.ROOT / "skills"
SKILL_FILES = sorted(SKILL_ROOT.rglob("*.md"))


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda path: str(path.relative_to(SKILL_ROOT)))
def test_skill_links_resolve(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)#\s]+)\)", text):
        if "://" not in target:
            assert (path.parent / target).exists(), f"{path.name}: broken link to {target}"


@pytest.mark.parametrize(
    "skill", sorted(SKILL_ROOT.glob("*/SKILL.md")), ids=lambda path: path.parent.name
)
def test_skill_entry_point_is_small_and_has_frontmatter(skill: Path) -> None:
    text = skill.read_text(encoding="utf-8")
    front = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert front, f"{skill.parent.name}: SKILL.md needs YAML frontmatter"
    assert re.search(rf"^name: {re.escape(skill.parent.name)}$", front.group(1), re.MULTILINE)
    description = re.search(r"^description: (.+)$", front.group(1), re.MULTILINE)
    assert description, f"{skill.parent.name}: SKILL.md needs a description"
    value = description.group(1)
    # An unquoted ": " or " #" makes the frontmatter invalid YAML, and installers skip the skill.
    if value[0] not in "'\"":
        assert ": " not in value and " #" not in value, (
            f"{skill.parent.name}: quote the description, or drop its ': ' and ' #'"
        )
    assert len(text.splitlines()) < 500, f"{skill.parent.name}: keep SKILL.md under 500 lines"
