from typing import Any

import shotgun_api3

from fpt.config import Config, Profile, load_config

SITE = "https://studio.example.com"
LOGIN_SCRIPT = ("auth", "login", "--site", "studio.example.com", "--script-name", "bot")


def test_login_stores_profile_and_secret_after_verifying(harness: Any) -> None:
    result = harness.run(*LOGIN_SCRIPT, stdin="the-key\n")
    assert result.code == 0
    assert result.json == {"profile": "default", "site": SITE, "auth": "script", "default": True}
    assert harness.secrets.get("default") == "the-key"
    assert load_config(harness.config_path) == Config(
        default="default",
        profiles={"default": Profile(name="default", site=SITE, auth="script", script_name="bot")},
    )
    credentials, _ = harness.built[0]
    assert (credentials.site, credentials.script_name, credentials.secret) == (
        SITE,
        "bot",
        "the-key",
    )
    assert harness.client.calls == [("find_one", ("Project", [], ["id"]), {})]


def test_login_never_echoes_the_secret(harness: Any) -> None:
    result = harness.run(*LOGIN_SCRIPT, stdin="the-key\n")
    assert "the-key" not in result.stdout + result.stderr
    assert "the-key" not in harness.config_path.read_text()


def test_login_with_rejected_credentials_stores_nothing(harness: Any) -> None:
    harness.client.errors["find_one"] = shotgun_api3.AuthenticationFault("Can't authenticate")
    result = harness.run(*LOGIN_SCRIPT, stdin="wrong\n")
    assert result.code == 3
    assert harness.secrets.get("default") is None
    assert not harness.config_path.exists()


def test_login_no_verify_skips_the_network(harness: Any) -> None:
    result = harness.run(*LOGIN_SCRIPT, "--no-verify", stdin="the-key\n")
    assert result.code == 0
    assert harness.built == []


def test_login_without_secret_on_stdin_is_a_usage_error(harness: Any) -> None:
    result = harness.run(*LOGIN_SCRIPT, stdin="")
    assert result.code == 2
    assert "stdin" in result.error["message"]
    assert not harness.config_path.exists()


def test_login_requires_site_and_auth_type_when_not_interactive(harness: Any) -> None:
    assert harness.run("auth", "login", "--script-name", "bot", stdin="k\n").code == 2
    assert harness.run("auth", "login", "--site", "x.example.com", stdin="k\n").code == 2


def test_login_rejects_two_auth_types(harness: Any) -> None:
    result = harness.run(*LOGIN_SCRIPT, "--login", "ada", stdin="k\n")
    assert result.code == 2
    assert "one of" in result.error["message"].lower()


def test_login_user_and_session_profiles(harness: Any) -> None:
    harness.run("auth", "login", "--name", "artist", "--site", SITE, "--login", "ada", stdin="pw\n")
    harness.run("auth", "login", "--name", "web", "--site", SITE, "--session", stdin="tok\n")
    config = load_config(harness.config_path)
    assert config.get("artist") == Profile(name="artist", site=SITE, auth="user", login="ada")
    assert config.get("web") == Profile(name="web", site=SITE, auth="session")
    assert config.default == "artist"
    assert harness.secrets.get("web") == "tok"


def test_login_with_otp_stores_the_session_not_the_password(harness: Any) -> None:
    harness.client.responses["get_session_token"] = "sess-1"
    result = harness.run(
        "auth", "login", "--site", SITE, "--login", "ada", "--otp", "123456", stdin="pw\n"
    )
    assert result.code == 0
    assert result.json["auth"] == "session"
    assert harness.built[0][0].auth_token == "123456"
    assert harness.secrets.get("default") == "sess-1"
    assert load_config(harness.config_path).get("default") == Profile(
        name="default", site=SITE, auth="session", login="ada"
    )


def test_otp_requires_login(harness: Any) -> None:
    assert harness.run(*LOGIN_SCRIPT, "--otp", "123456", stdin="k\n").code == 2


def test_login_stores_proxy_and_ca_certs(harness: Any) -> None:
    harness.run(
        *LOGIN_SCRIPT, "--http-proxy", "proxy:3128", "--ca-certs", "/etc/ca.pem", stdin="k\n"
    )
    profile = load_config(harness.config_path).get("default")
    assert (profile.http_proxy, profile.ca_certs) == ("proxy:3128", "/etc/ca.pem")
    assert harness.built[0][0].ca_certs == "/etc/ca.pem"


def test_stored_profile_is_used_by_other_commands(harness: Any) -> None:
    harness.run(*LOGIN_SCRIPT, stdin="the-key\n")
    harness.client.responses["info"] = {"version": [8, 60, 0]}
    result = harness.run("info")
    assert result.code == 0
    assert harness.built[-1][0].source == "profile:default"


def test_list_shows_profiles_and_marks_default(harness: Any) -> None:
    harness.run(*LOGIN_SCRIPT, stdin="k\n")
    harness.run("auth", "login", "--name", "artist", "--site", SITE, "--login", "ada", stdin="pw\n")
    assert harness.run("auth", "list").json == [
        {"name": "artist", "site": SITE, "auth": "user", "identity": "ada", "default": False},
        {"name": "default", "site": SITE, "auth": "script", "identity": "bot", "default": True},
    ]


def test_list_with_no_profiles_is_an_empty_list(harness: Any) -> None:
    assert harness.run("auth", "list").json == []


def test_use_changes_default(harness: Any) -> None:
    harness.run(*LOGIN_SCRIPT, stdin="k\n")
    harness.run("auth", "login", "--name", "artist", "--site", SITE, "--login", "ada", stdin="pw\n")
    assert harness.run("auth", "use", "artist").json == {"default": "artist"}
    assert load_config(harness.config_path).default == "artist"


def test_use_unknown_profile_is_a_usage_error(harness: Any) -> None:
    assert harness.run("auth", "use", "nope").code == 2


def test_logout_removes_profile_and_secret(harness: Any) -> None:
    harness.run(*LOGIN_SCRIPT, stdin="k\n")
    assert harness.run("auth", "logout").json == {"removed": "default", "default": None}
    assert harness.secrets.get("default") is None
    assert load_config(harness.config_path) == Config()


def test_logout_with_nothing_to_remove_is_a_usage_error(harness: Any) -> None:
    assert harness.run("auth", "logout").code == 2


def test_status_reports_verified_credentials(harness: Any) -> None:
    harness.use_script_env()
    assert harness.run("auth", "status").json == {
        "site": "https://env.example.com",
        "auth": "script",
        "identity": "envbot",
        "source": "env",
        "ok": True,
    }
    assert harness.client.calls == [("find_one", ("Project", [], ["id"]), {})]


def test_status_with_bad_credentials_exits_3(harness: Any) -> None:
    harness.use_script_env()
    harness.client.errors["find_one"] = shotgun_api3.AuthenticationFault("nope")
    assert harness.run("auth", "status").code == 3


def test_token_prints_session_token(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["get_session_token"] = "abc123"
    assert harness.run("auth", "token").json == "abc123"
