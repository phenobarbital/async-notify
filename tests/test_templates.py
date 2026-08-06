"""Offline unit suite for FEAT-002 (TemplateParser refactor).

Covers the 30 unit tests enumerated in
``sdd/specs/templateparser-refactor.spec.md`` §4, exercising:

  - Construction & configuration (TASK-007): :class:`JinjaConfig`, the
    tolerant/optional directory handling, extension loading, and the
    whitespace/autoescape/undefined defaults.
  - Public API (TASK-008): in-memory templates, runtime directory
    registration, ``render_string``/``render_string_async``, globals,
    bulk filter registration, and the explicit ``compile_directory``.
  - Defect regressions (TASK-009): the ``add_filter()`` name-resolution
    bug and the ``"NAV: "``/``"Notify: "`` error-prefix inconsistency.

Everything here runs fully offline; every directory is created under
``tmp_path``.
"""
import asyncio
from pathlib import Path

import pytest
from jinja2 import Environment, UndefinedError

from notify import templates
from notify.templates import JinjaConfig, TemplateParser

# ---------------------------------------------------------------- fixtures

@pytest.fixture
def template_dir(tmp_path: Path) -> Path:
    """Minimal on-disk template set."""
    d = tmp_path / "templates"
    d.mkdir()
    (d / "hello.html").write_text("Hello {{ name }}!", encoding="utf-8")
    (d / "raw.html").write_text("{{ value }}", encoding="utf-8")
    return d


@pytest.fixture
def parser(template_dir: Path) -> TemplateParser:
    return TemplateParser(directory=template_dir)


# ---------------------------------------------------------- construction (TASK-007)

def test_init_legacy_directory_path(template_dir: Path):
    """``TemplateParser(directory=Path(...))`` still constructs and renders."""
    p = TemplateParser(directory=Path(template_dir))
    assert p.render("hello.html", {"name": "Ada"}) == "Hello Ada!"


def test_init_accepts_str_directory(template_dir: Path):
    """``directory=`` accepts ``str`` as well as ``Path``."""
    p = TemplateParser(directory=str(template_dir))
    assert p.path == template_dir.resolve()
    assert p.render("hello.html", {"name": "Ada"}) == "Hello Ada!"


def test_init_missing_dir_warns_not_raises(tmp_path: Path):
    """Absent directory degrades to memory-only mode instead of raising.

    ``strict_directory=True`` restores the legacy ``RuntimeError``.
    """
    missing = tmp_path / "does-not-exist"
    p = TemplateParser(directory=missing)
    assert p.path is None
    assert p.environment is not None

    with pytest.raises(RuntimeError):
        TemplateParser(directory=missing, strict_directory=True)


def test_init_does_not_write_compiled_artifact(template_dir: Path):
    """Construction writes nothing into the template directory."""
    TemplateParser(directory=template_dir)
    assert not (template_dir / ".compiled").exists()


def test_config_dict_legacy_merge(template_dir: Path):
    """``config={"enable_async": False}`` shallow-merges over the defaults."""
    p = TemplateParser(directory=template_dir, config={"enable_async": False})
    assert p.environment.is_async is False


def test_config_instance_not_mutated(template_dir: Path):
    """A shared ``JinjaConfig`` must not accumulate directories (spec §7 R7)."""
    cfg = JinjaConfig()
    TemplateParser(directory=template_dir, config=cfg)
    TemplateParser(directory=template_dir, config=cfg)
    assert cfg.template_dirs == []


def test_template_debug_does_not_leak(template_dir: Path, monkeypatch):
    """``TEMPLATE_DEBUG=True`` does not leak ``jinja2.ext.debug`` (spec §1.5)."""
    monkeypatch.setattr(templates.nav_config, "getboolean", lambda *a, **kw: True)
    p1 = TemplateParser(directory=template_dir)
    assert "jinja2.ext.DebugExtension" in p1.environment.extensions

    monkeypatch.setattr(templates.nav_config, "getboolean", lambda *a, **kw: False)
    p2 = TemplateParser(directory=template_dir)
    assert "jinja2.ext.DebugExtension" not in p2.environment.extensions


def test_optional_extension_missing_is_tolerated(template_dir: Path, monkeypatch):
    """A missing third-party extension is skipped with a warning; construction succeeds."""
    orig_import_module = templates.importlib.import_module

    def fake_import(name, *args, **kwargs):
        if name in {"jinja2_time", "jinja2_iso8601", "jinja2_humanize_extension"}:
            raise ImportError(name)
        return orig_import_module(name, *args, **kwargs)

    monkeypatch.setattr(templates.importlib, "import_module", fake_import)
    p = TemplateParser(directory=template_dir)
    assert p.render("hello.html", {"name": "x"}) == "Hello x!"


def test_multiple_template_dirs_precedence(tmp_path: Path):
    """With two dirs holding the same filename, the first wins."""
    d1 = tmp_path / "d1"
    d1.mkdir()
    d2 = tmp_path / "d2"
    d2.mkdir()
    (d1 / "dup.html").write_text("FROM_D1", encoding="utf-8")
    (d2 / "dup.html").write_text("FROM_D2", encoding="utf-8")

    p = TemplateParser(directory=d1, template_dirs=[d2])
    assert p.render("dup.html") == "FROM_D1"


def test_autoescape_off_by_default(parser: TemplateParser):
    """Autoescape is off by default — proves production behaviour is untouched."""
    assert parser.render_string("{{ '<b>x</b>' }}") == "<b>x</b>"


def test_autoescape_opt_in(template_dir: Path):
    """``autoescape=True`` escapes the same input."""
    p = TemplateParser(directory=template_dir, autoescape=True)
    assert p.render_string("{{ '<b>x</b>' }}") == "&lt;b&gt;x&lt;/b&gt;"


def test_undefined_permissive_by_default(parser: TemplateParser):
    """A missing variable renders as an empty string by default."""
    assert parser.render_string("{{ missing_var }}") == ""


def test_strict_undefined_opt_in(template_dir: Path):
    """``strict_undefined=True`` raises on a missing variable.

    ``jinja2.UndefinedError`` is a ``TemplateError`` subclass, so
    ``render_string`` wraps it as ``ValueError`` per its documented
    exception-handling shape.
    """
    p = TemplateParser(directory=template_dir, strict_undefined=True)
    with pytest.raises(ValueError) as exc_info:
        p.render_string("{{ missing_var }}")
    assert isinstance(exc_info.value.__cause__, UndefinedError)


def test_whitespace_defaults_unchanged(parser: TemplateParser):
    """``trim_blocks``/``lstrip_blocks``/``keep_trailing_newline`` default to Jinja2's ``False``."""
    assert parser.environment.trim_blocks is False
    assert parser.environment.lstrip_blocks is False
    assert parser.environment.keep_trailing_newline is False


# --------------------------------------------------------------- public API (TASK-008)

def test_add_template_dir_runtime(tmp_path: Path, parser: TemplateParser):
    """A directory added post-construction resolves its templates."""
    other = tmp_path / "other"
    other.mkdir()
    (other / "other.html").write_text("OTHER {{ x }}", encoding="utf-8")

    parser.add_template_dir(other)
    assert parser.render("other.html", {"x": "Y"}) == "OTHER Y"


def test_add_templates_in_memory(parser: TemplateParser):
    """An in-memory template renders."""
    parser.add_templates({"mem.html": "MEM {{ x }}"})
    assert parser.render("mem.html", {"x": "1"}) == "MEM 1"


def test_in_memory_shadows_filesystem(parser: TemplateParser):
    """An in-memory template with the same name takes precedence over the on-disk one."""
    parser.add_templates({"hello.html": "OVERRIDDEN"})
    assert parser.render("hello.html") == "OVERRIDDEN"


def test_render_sync_backward_compat(parser: TemplateParser):
    """``render(name, params)`` matches the 1.5.7 behaviour."""
    assert parser.render("hello.html", {"name": "Pilar"}) == "Hello Pilar!"


def test_render_async_backward_compat(parser: TemplateParser):
    """``await render_async(name, params)`` matches ``render()`` output.

    Deliberately a plain (non-``async def``) test: with
    ``enable_async=True``, Jinja2's *synchronous* ``render()`` internally
    drives the async code path via ``asyncio.run()`` (spec §7 R4,
    pre-existing and out of scope). Calling the sync ``render()``/
    ``render_string()`` methods from inside an already-running event loop
    (i.e. from a ``pytest-asyncio``-wrapped ``async def`` test) reproduces
    that hazard. Driving the coroutine explicitly via ``asyncio.run()``
    from a synchronous test avoids ever nesting event loops.
    """
    sync_result = parser.render("hello.html", {"name": "Pilar"})
    async_result = asyncio.run(parser.render_async("hello.html", {"name": "Pilar"}))
    assert async_result == sync_result


def test_render_string_sync_and_async(parser: TemplateParser):
    """Both ``render_string`` variants render ``"Hi {{ who }}"``.

    See :func:`test_render_async_backward_compat` for why this stays a
    plain synchronous test (spec §7 R4).
    """
    assert parser.render_string("Hi {{ who }}", {"who": "there"}) == "Hi there"
    result = asyncio.run(parser.render_string_async("Hi {{ who }}", {"who": "there"}))
    assert result == "Hi there"


def test_add_globals(parser: TemplateParser):
    """A registered global is visible to templates."""
    parser.add_globals({"app": "notify"})
    assert parser.render_string("{{ app }}") == "notify"


def test_add_filters_mapping(parser: TemplateParser):
    """Bulk filter registration works."""
    parser.add_filters({"shout": lambda v: str(v).upper()})
    assert parser.render_string("{{ 'hi' | shout }}") == "HI"


def test_get_template_missing_raises_filenotfound(parser: TemplateParser):
    """``get_template("nope.html")`` raises ``FileNotFoundError`` (unchanged)."""
    with pytest.raises(FileNotFoundError):
        parser.get_template("nope.html")


def test_environment_property(parser: TemplateParser):
    """``environment`` returns the live ``jinja2.Environment``."""
    assert isinstance(parser.environment, Environment)
    assert parser.environment is parser.env


def test_compile_directory_explicit(tmp_path: Path, parser: TemplateParser):
    """``compile_directory(tmp_path)`` produces the artifact on demand."""
    target = tmp_path / "compiled.zip"
    parser.compile_directory(target)
    assert target.exists()


def test_compile_directory_noop_without_directories(tmp_path: Path):
    """``compile_directory`` is a no-op for a memory-only parser."""
    target = tmp_path / "should-not-be-created.zip"
    p = TemplateParser()
    p.compile_directory(target)
    assert not target.exists()


def test_bytecode_cache_opt_in(tmp_path: Path, template_dir: Path):
    """``bytecode_cache_dir=`` creates the dir and populates it after a render."""
    cache_dir = tmp_path / "cache"
    p = TemplateParser(directory=template_dir, bytecode_cache_dir=cache_dir)
    assert cache_dir.exists()

    p.render("hello.html", {"name": "x"})
    assert any(cache_dir.iterdir())


# ------------------------------------------------------------- defect regressions (TASK-009)

def test_add_filter_without_name_uses_func_name(parser: TemplateParser):
    """Regression for the ``templates.py:94`` bug: no explicit name uses ``func.__name__``."""
    def my_filter(v):
        return v

    parser.add_filter(my_filter)
    assert "my_filter" in parser.environment.filters


def test_add_filter_with_explicit_name(parser: TemplateParser):
    """Explicit ``name=`` still wins."""
    def my_filter(v):
        return v

    parser.add_filter(my_filter, name="custom")
    assert "custom" in parser.environment.filters
    assert "my_filter" not in parser.environment.filters


def test_add_filter_non_callable_raises_typeerror(parser: TemplateParser):
    """Non-callable input raises ``TypeError`` — even with an explicit ``name=``."""
    with pytest.raises(TypeError):
        parser.add_filter("not-a-function")
    with pytest.raises(TypeError):
        parser.add_filter("not-a-function", name="x")


async def test_error_prefix_is_notify(parser: TemplateParser):
    """A render failure message starts with ``"Notify:"``, never ``"NAV:"``."""
    def boom(_value):
        raise ValueError("boom")

    parser.add_filters({"boom": boom})
    parser.add_templates({"boom.html": "{{ x | boom }}"})

    with pytest.raises(RuntimeError) as exc_info:
        await parser.render_async("boom.html", {"x": 1})

    message = str(exc_info.value)
    assert message.startswith("Notify:")
    assert "NAV:" not in message
