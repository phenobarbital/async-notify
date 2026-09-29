"""Configuration and dependency-manifest regression tests (FEAT-004, M9)."""

from pathlib import Path

import tomllib

from notify import conf

PYPROJECT_PATH = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _load_pyproject() -> dict:
    with open(PYPROJECT_PATH, "rb") as fh:
        return tomllib.load(fh)


def test_o365_settings_defaults():
    assert conf.O365_TOKEN_STORE == "memory"
    assert conf.O365_TOKEN_STORE_TTL == 0
    assert conf.O365_TOKEN_ALLOW_UNENCRYPTED is False
    assert conf.O365_TOKEN_STORE_DIR.endswith(".o365")
    assert conf.O365_TOKEN_STORE_REDIS == conf.NOTIFY_REDIS


def test_o365_settings_exist():
    for name in (
        "O365_AUTH_FLOW",
        "O365_SENDER",
        "O365_CLIENT_CERTIFICATE_PATH",
        "O365_CLIENT_CERTIFICATE_THUMBPRINT",
        "O365_CLIENT_CERTIFICATE_PASSWORD",
        "O365_TOKEN_STORE",
        "O365_TOKEN_STORE_DIR",
        "O365_TOKEN_STORE_REDIS",
        "O365_TOKEN_STORE_TTL",
        "O365_TOKEN_CIPHER_KEY",
        "O365_TOKEN_ALLOW_UNENCRYPTED",
    ):
        assert hasattr(conf, name), f"missing setting {name}"


def test_legacy_azure_packages_removed_from_extras():
    data = _load_pyproject()
    extras = data["project"]["optional-dependencies"]
    for extra_name in ("azure", "all"):
        deps = " ".join(extras[extra_name]).lower()
        assert "pyo365" not in deps
        assert "office365-rest-python-client" not in deps
        # `o365` package (not the substring inside "office365" package names)
        assert not any(dep.lower().startswith("o365") for dep in extras[extra_name])


def test_cryptography_explicit_in_azure_and_all_extras():
    data = _load_pyproject()
    extras = data["project"]["optional-dependencies"]
    for extra_name in ("azure", "all"):
        deps = extras[extra_name]
        assert any(dep.lower().startswith("cryptography>=42.0") for dep in deps), extra_name
