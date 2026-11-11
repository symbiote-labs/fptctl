---
name: fpt-library-upgrade
description: Upgrade the fpt CLI (symbiote-labs/fpt-cli) to a new shotgun_api3 release and get it verified and released. Use when a "shotgun-api3 X is out" issue appears, when the Library watch workflow reports a new version, when someone asks to bump, follow or support a newer shotgun_api3 / ShotGrid Python API, or when the parity burndown shows new library methods or parameters with no case.
metadata:
  internal: true
---

# Upgrading fpt to a new shotgun_api3

fpt pins one exact library version (`shotgun-api3==X` in `pyproject.toml`), because the parity
suite has verified only that version against a live site. Following a new release means moving
the pin, covering whatever the new version adds, proving it with parity, and releasing. The aim is
to ship within days of the library, so keep each upgrade small: the pin, the new surface, nothing
else.

## How a new release is noticed

The `Library watch` workflow (`.github/workflows/library-watch.yml`) runs daily. When PyPI has a
release newer than the pin, it opens one issue per version, "shotgun-api3 X is out", listing the
public methods and signatures that were added, removed or changed. The same report runs locally:

```shell
uv run python -m scripts.library_watch
```

It reads both versions in throw-away environments (`scripts/api_signatures.py`), using the parity
inventory's rule for what counts as public. Read the upstream `HISTORY.rst` too: behaviour can
change without a signature changing.

## The upgrade

1. **Branch and pin.** Set `shotgun-api3==X` in `pyproject.toml`, run `uv lock`, and change the
   version named in `README.md` (a test checks the README names the pinned version).
2. **Run the gate.** `uv run ruff format --check . && uv run ruff check . && uv run mypy src parity
   scripts && uv run pytest`. A failure here is a behaviour change in the library; read it before
   changing anything.
3. **List what is new.** Every new public method and parameter becomes a burndown item. Run
   parity (below) and look at `BURNDOWN.md` for `no_case` items, or work from the issue's diff.
4. **Give each new item a surface,** following the rules already in the code:
   - A **new method** is reachable at once through `fpt api call`, because `fpt api methods`
     reads the library at run time. It gets a designed command only if it belongs with an
     existing command group's purpose; otherwise its surface is `api call`, and it needs a
     parity case in `parity/cases/api.json`.
   - A **new parameter of a method that has a command** needs an option on that command: a
     designed command exposes every parameter of its method. Add the option, its help text, a
     CLI test that asserts the exact library call, a mention in the docstring if it changes
     behaviour, and a parity case that passes a non-default value. The only exception is a
     parameter the library deprecates; that goes under `[not_exposed]` in
     `parity/dimensions.toml` with a reason.
   - A **removed method or parameter** means removing its option, its cases and any
     `[surfaces]` entry, and saying so in the release notes, because it breaks users.
   - New filter operators, data types or enum values go into `parity/dimensions.toml`, then
     `uv run python -m parity.generate` rewrites the generated cases.
5. **Regenerate the skill docs.** `uv run python -m scripts.skill_docs`. The pre-commit hook
   (`git config core.hooksPath .githooks`) and CI both fail on stale docs, and the docstring tests
   fail on a command with no description or examples.
6. **Prove it with parity,** then release with the `fpt-release` skill.

## Parity, briefly

Parity is the definition of done. For each case in `parity/cases/*.json` the runner calls the
library directly and then runs the `fpt` command line, and requires the same request (from
fpt's call trace) and the same result. `uv run python -m parity.burndown --strict` exits 0 only
when every inventory item is done or waived, the results come from a run at the current commit
on a clean tree, and the gate is green.

- Run it with the **Parity** workflow (Actions, "Run workflow"), which uses the repository's
  `FPT_TEST_*` secrets, or locally with those variables set: `uv run python -m parity.runner`,
  then `uv run python -m parity.burndown --strict`. It creates a project on the sandbox site and
  retires it at the end; never point it at a production site.
- A case is data: copy the shape of a neighbouring case. For example, from `api.json`:
  `{"id": "...", "method": "work_schedule_read", "mode": "identical", "args": {...}, "argv":
  ["api", "call", "work_schedule_read", "--args", "..."]}`. Modes: `identical` for reads,
  `mirrored` for writes on each side's own fixture, `bytes` for downloads, `error` for faults.
- The module docstrings in `parity/` explain the runner, fixtures, generated cases and burndown.

Three rules keep parity honest, and they are not yours to bend:

- **Waivers belong to the owner.** `parity/waivers.toml` lists items accepted as unverifiable,
  each with a reason and evidence. Propose a waiver with the evidence; never add one yourself.
  When a library fix makes a waived item verifiable (for example `user_subscriptions_create`,
  python-api issue #463), propose removing the waiver.
- **`parity/compare.py` and `parity/runner.py` change only with the owner's approval,** in their
  own commit with the reason. Never change them to make a case pass. If fpt's output differs from
  the library's, fpt is wrong.
- **Nothing is marked done by hand.** An item is done only because a passing case covered it.

## When to stop and ask

Stop and ask the owner when the library removes or changes something users rely on, when an
item cannot be made to pass (it stays remaining, with the evidence), or when the upgrade seems
to need a new fpt feature rather than a new option or case.
