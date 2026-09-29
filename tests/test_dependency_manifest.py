"""Dependency-manifest and documentation-parity tests (FEAT-005, M2/M4).

Locks spec §5 goals G3 (slim core), G4 (an extra per provider SDK) and the
README-parity half of G5. Pure file parsing — no network, no install.
"""

import re
import tomllib
from pathlib import Path

import pytest

from notify.notify import PROVIDER_EXTRAS

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
README_PATH = REPO_ROOT / "README.md"

#: Packages that must not be installed by the bare `async-notify` distribution.
BANNED_FROM_CORE = ("pillow", "emoji", "aiobotocore", "cloudpickle")


def _load_pyproject() -> dict:
    """Parse ``pyproject.toml`` — same idiom as tests/test_office365_configuration.py."""
    with open(PYPROJECT_PATH, "rb") as fh:
        return tomllib.load(fh)


def _dist_name(requirement: str) -> str:
    """Normalise a PEP 508 requirement string to its PEP 503 distribution name.

    Handles environment markers (``; sys_platform != 'win32'``), extras
    brackets (``navconfig[default]``) and every version specifier form.

    Args:
        requirement: A raw entry from ``dependencies`` or an extra.

    Returns:
        The lowercased, dash-normalised distribution name.
    """
    name = requirement.split(";", 1)[0]
    name = name.split("[", 1)[0]
    name = re.split(r"[<>=!~\s]", name, maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", name.strip().lower())


@pytest.mark.parametrize(
    ("requirement", "expected"),
    [
        ("aiobotocore>=2.15.2", "aiobotocore"),
        ("uvloop>=0.20.0; sys_platform != 'win32'", "uvloop"),
        ("navconfig[default]>=2.2.0", "navconfig"),
        ("slack_bolt>=1.18.0", "slack-bolt"),
        ("slack-bolt", "slack-bolt"),
        ("onesignal-sdk>=2.0.0", "onesignal-sdk"),
    ],
)
def test_dist_name_normalises_requirements(requirement, expected):
    """The normaliser handles markers, extras brackets and PEP 503 spellings."""
    assert _dist_name(requirement) == expected


def test_core_dependencies_are_minimal():
    """AC-G3 — the four demoted packages are gone from core; aiohttp is in."""
    core = {_dist_name(d) for d in _load_pyproject()["project"]["dependencies"]}
    for banned in BANNED_FROM_CORE:
        assert _dist_name(banned) not in core, f"{banned} must not be a core dependency"
    assert "aiohttp" in core, "aiohttp must be promoted into core"


def test_provider_extras_names_exist_in_pyproject():
    """AC-G4 — every PROVIDER_EXTRAS value names a real extra."""
    extras = set(_load_pyproject()["project"]["optional-dependencies"])
    unknown = {v for v in PROVIDER_EXTRAS.values() if v not in extras}
    assert not unknown, f"PROVIDER_EXTRAS names non-existent extras: {sorted(unknown)}"


def test_all_extra_is_a_superset():
    """AC-G4 — `all` contains every distribution from every non-dev extra."""
    extras = _load_pyproject()["project"]["optional-dependencies"]
    in_all = {_dist_name(d) for d in extras["all"]}
    missing = [
        f"{extra}:{_dist_name(dep)}"
        for extra, deps in extras.items()
        if extra not in ("all", "dev")
        for dep in deps
        if _dist_name(dep) not in in_all
    ]
    assert not missing, f"`all` extra is missing: {missing}"


def test_azure_invariants_preserved():
    """AC-G4 — re-assert tests/test_office365_configuration.py:42-58.

    That file must keep passing unmodified; this is a second, local guard so a
    manifest edit fails here too, next to the rest of the manifest contract.
    """
    extras = _load_pyproject()["project"]["optional-dependencies"]
    for name in ("azure", "all"):
        deps = extras[name]
        assert any(d.lower().startswith("cryptography>=42.0") for d in deps), name
        joined = " ".join(deps).lower()
        assert "pyo365" not in joined, name
        assert "office365-rest-python-client" not in joined, name
        assert not any(d.lower().startswith("o365") for d in deps), name


def test_readme_matrix_matches_manifest():
    """AC-G5 — every non-dev extra is documented, and vice versa.

    The citation form is ``async-notify[<extra>]`` or a backticked ```<extra>```.
    """
    extras = set(_load_pyproject()["project"]["optional-dependencies"]) - {"dev"}
    readme = README_PATH.read_text(encoding="utf-8")
    undocumented = {e for e in extras if f"async-notify[{e}]" not in readme and f"`{e}`" not in readme}
    assert not undocumented, f"extras missing from README (cite as `async-notify[<extra>]`): {sorted(undocumented)}"
    cited = set(re.findall(r"async-notify\[([A-Za-z0-9_.-]+)\]", readme))
    unknown = cited - extras
    assert not unknown, f"README cites async-notify[...] extras that do not exist: {sorted(unknown)}"
