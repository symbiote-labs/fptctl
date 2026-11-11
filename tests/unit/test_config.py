import stat
from pathlib import Path

import pytest

from fptctl.config import Config, Profile, default_config_path, load_config, save_config
from fptctl.errors import UsageError

STUDIO = Profile(
    name="studio", site="https://studio.example.com", auth="script", script_name="fptctl"
)
ARTIST = Profile(name="artist", site="https://studio.example.com", auth="user", login="ada")


def test_identity_depends_on_auth_type() -> None:
    assert STUDIO.identity == "fptctl"
    assert ARTIST.identity == "ada"
    assert Profile(name="s", site="https://x", auth="session").identity is None


def test_first_profile_becomes_default() -> None:
    config = Config().with_profile(STUDIO).with_profile(ARTIST)
    assert config.default == "studio"
    assert set(config.profiles) == {"studio", "artist"}


def test_with_profile_does_not_mutate_the_original() -> None:
    empty = Config()
    empty.with_profile(STUDIO)
    assert empty.profiles == {}
    assert empty.default is None


def test_with_profile_replaces_same_name() -> None:
    moved = Profile(name="studio", site="https://other.example.com", auth="script", script_name="x")
    config = Config().with_profile(STUDIO).with_profile(moved)
    assert config.get("studio") == moved


def test_with_default_requires_existing_profile() -> None:
    config = Config().with_profile(STUDIO).with_profile(ARTIST)
    assert config.with_default("artist").default == "artist"
    with pytest.raises(UsageError, match="No profile named 'nope'"):
        config.with_default("nope")


def test_without_profile_moves_default_to_a_remaining_profile() -> None:
    config = Config().with_profile(STUDIO).with_profile(ARTIST).without_profile("studio")
    assert config.default == "artist"
    assert config.get("studio") is None


def test_without_last_profile_clears_default() -> None:
    assert Config().with_profile(STUDIO).without_profile("studio") == Config()


def test_without_unknown_profile_is_a_usage_error() -> None:
    with pytest.raises(UsageError, match="No profile named 'nope'"):
        Config().without_profile("nope")


def test_load_missing_file_gives_empty_config(tmp_path: Path) -> None:
    assert load_config(tmp_path / "config.toml") == Config()


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "config.toml"
    config = Config().with_profile(STUDIO).with_profile(ARTIST).with_default("artist")
    save_config(config, path)
    assert load_config(path) == config


def test_saved_file_is_private_and_has_no_null_fields(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    save_config(Config().with_profile(STUDIO), path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    text = path.read_text()
    assert "login" not in text
    assert 'script_name = "fptctl"' in text


def test_load_rejects_invalid_toml(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("not = [valid")
    with pytest.raises(UsageError, match="Cannot read config file"):
        load_config(path)


def test_load_rejects_unknown_auth_type(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[profiles.x]\nsite = "https://x"\nauth = "magic"\n')
    with pytest.raises(UsageError, match="profile 'x'"):
        load_config(path)


def test_default_config_path_precedence() -> None:
    home = Path.home()
    assert default_config_path({}) == home / ".config" / "fptctl" / "config.toml"
    assert default_config_path({"XDG_CONFIG_HOME": "/xdg"}) == Path("/xdg/fptctl/config.toml")
    assert default_config_path({"FPTCTL_CONFIG": "/a/b.toml", "XDG_CONFIG_HOME": "/xdg"}) == Path(
        "/a/b.toml"
    )
