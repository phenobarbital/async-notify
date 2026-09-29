"""Startup-import deferral tests (FEAT-005, M3).

Locks spec §5 goal G6. Every `sys.modules` assertion runs in a CLEAN
SUBPROCESS: the existing suite imports TemplateParser and TemplateEnv at
collection time (tests/test_jinja_string_templates.py:28,
tests/test_templates_integration.py), so an in-process check would be
vacuous — see spec §4.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Modules that must NOT be resident after a bare `import notify`.
DEFERRED = ("jinja2", "datamodel")

#: AC-G6 cold-import ceiling, in milliseconds.
IMPORT_BUDGET_MS = 175.0


def _run(code: str) -> str:
    """Run *code* in a clean interpreter rooted at the repo and return stdout.

    Args:
        code: Python source executed via ``-c``.

    Returns:
        Stripped stdout. Raises ``AssertionError`` with stderr attached when
        the child exits non-zero, so a failure shows the traceback.
    """
    env = {**os.environ, "PYTHONPATH": "."}
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, f"subprocess failed ({result.returncode}):\n{result.stderr}"
    # navconfig's logger may write to stdout; the last line is our payload.
    lines = result.stdout.strip().splitlines()
    return lines[-1].strip() if lines else ""


def test_import_notify_defers_heavy_modules():
    """AC-G6 — `import notify` leaves jinja2 and datamodel out of sys.modules."""
    out = _run("""
        import sys
        import notify
        print(" ".join(m for m in ("jinja2", "datamodel") if m in sys.modules) or "clean")
        """)
    assert out == "clean", f"still resident after `import notify`: {out}"


def test_deferred_modules_load_on_first_use():
    """AC-G6 — deferral, not deletion: jinja2 appears after first template use."""
    out = _run("""
        import sys
        import notify
        import notify.notify as n
        before = "jinja2" in sys.modules
        n.TemplateEnv
        print(f"{before} {'jinja2' in sys.modules}")
        """)
    assert out == "False True", f"expected jinja2 absent then resident, got: {out}"


def test_utils_templates_has_no_heavy_imports():
    """Importing notify.utils.templates pulls in neither jinja2 nor datamodel.

    ``navconfig`` is deliberately not asserted: importing any ``notify.*``
    submodule first runs ``notify/__init__.py``, which imports navconfig
    (out of scope for FEAT-005, spec §1 Non-Goals).
    """
    out = _run("""
        import sys
        import notify.utils.templates  # noqa: F401
        heavy = [m for m in ("jinja2", "datamodel") if m in sys.modules]
        print(" ".join(heavy) or "clean")
        """)
    assert out == "clean", f"notify.utils.templates dragged in: {out}"


def test_is_template_source_reexported():
    """The compatibility re-export works, SILENTLY, with the same value."""
    out = _run("""
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            from notify.templates import is_template_source, JINJA_MARKERS
        assert is_template_source("{{ x }}") and not is_template_source("file.html")
        print(len(caught), "|".join(JINJA_MARKERS))
        """)
    assert out == "0 {{|{%|{#", f"unexpected re-export result: {out}"


def test_actor_annotation_no_longer_resolves():
    """Pin the ACCEPTED behaviour change from spec §7.

    ``typing.get_type_hints()`` on ProviderBase / ThreadMessage methods no
    longer resolves ``Actor``: PEP 563 makes it a string and the deferred
    ``TYPE_CHECKING`` import means module globals cannot resolve it. The repo
    has zero ``get_type_hints`` callers; this test makes the change a recorded
    decision rather than a surprise.
    """
    out = _run("""
        import typing
        from notify.providers.base import ProviderBase
        from notify.providers.message import ThreadMessage
        import sys
        assert "datamodel" not in sys.modules
        results = []
        for fn in (ProviderBase._prepare_, ThreadMessage.__init__):
            try:
                typing.get_type_hints(fn)
                results.append("resolved")
            except NameError:
                results.append("NameError")
        # Documented workaround: inject Actor where the hints are evaluated.
        from notify.models import Actor
        typing.get_type_hints(ProviderBase._prepare_, localns={"Actor": Actor})
        print(" ".join(results))
        """)
    assert out == "NameError NameError", f"unexpected get_type_hints behaviour: {out}"


def test_import_notify_within_budget():
    """AC-G6 — cold `import notify` stays within the spec threshold."""
    timings = []
    residency = ""
    for _ in range(5):
        out = _run("""
            import sys, time
            start = time.perf_counter()
            import notify
            elapsed = (time.perf_counter() - start) * 1000
            resident = ",".join(m for m in ("jinja2", "datamodel") if m in sys.modules) or "none"
            print(f"{elapsed:.1f} {resident}")
            """)
        elapsed, residency = out.split()
        timings.append(float(elapsed))
    best = min(timings)
    assert best <= IMPORT_BUDGET_MS, (
        f"cold `import notify` took {best:.1f} ms (runs: {timings}); budget {IMPORT_BUDGET_MS} ms; "
        f"deferred modules resident: {residency}"
    )
