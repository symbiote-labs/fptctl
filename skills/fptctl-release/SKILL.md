---
name: fptctl-release
description: Cut a release of the fptctl CLI (symbiote-labs/fptctl) by choosing the version, proving it with the parity suite, tagging it, and publishing the GitHub release. Use when someone asks to release, tag, ship or publish fptctl, to bump fptctl's version, or after a shotgun_api3 upgrade is ready to go out.
metadata:
  internal: true
---

# Releasing fptctl

A release is a tag `vX.Y.Z` on `main` whose commit passed the full parity suite. Pushing the tag
runs `.github/workflows/release.yml`, which checks the tag matches the package version, runs the
gate, builds the wheel and sdist, and creates a **draft** GitHub release with them. A person
writes the notes and publishes it. Users install with
`uv tool install git+https://github.com/symbiote-labs/fptctl@vX.Y.Z`.

## Steps

1. **Start from a green `main`.** CI passes, and the working tree is clean.
2. **Choose the version** in `src/fptctl/__init__.py`, semver-style:
   - patch: a library patch release with no new surface, or a bug fix;
   - minor: new options or commands (usually from a library upgrade);
   - major: anything that removes or changes a command, an option, an exit code or the JSON shape.
3. **Update the version everywhere it is named.** `README.md`'s install lines name the tag
   (`fptctl@vX.Y.Z`); a test fails until they match `__version__`. Run
   `uv run python -m scripts.skill_docs` in case the docs changed.
4. **Commit** with a short message, such as `release: 0.2.0`, and push to `main`.
5. **Run parity at that exact commit.** Use the **Parity** workflow on `main`, or run it locally
   on a clean tree: `uv run python -m parity.runner`, then
   `uv run python -m parity.burndown --strict`, which must exit 0. The burndown refuses results
   from any other commit, so do not commit again between this run and the tag.
6. **Tag and push:** `git tag -a vX.Y.Z -m "fptctl X.Y.Z"` and `git push origin vX.Y.Z`. The Release
   workflow drafts the GitHub release.
7. **Write the notes** in the draft and publish it. Say what changed for users, which
   `shotgun_api3` version the release is built on, and anything that breaks. Keep it short and
   plain; the commit list GitHub generates is a starting point, not the notes.
8. **Check the install** from a clean environment:
   `uv tool run --isolated --from git+https://github.com/symbiote-labs/fptctl@vX.Y.Z fptctl --version`.

## Things that go wrong

- **The tag does not match the version:** the Release workflow fails at its first step. Delete the
  tag locally and on GitHub, fix `__version__`, and start again from step 4.
- **Parity is stale:** any commit after the parity run makes the burndown stale. Run it again at
  the commit you will tag.
- **A parity item fails:** do not release. Fix fptctl, or raise it with the owner; waivers are the
  owner's decision (see the `fptctl-library-upgrade` skill).
- **Push access:** releases are made from an account with write access to `symbiote-labs`. Check
  which account `gh` and git will use before tagging (`gh api user --jq .login`).
