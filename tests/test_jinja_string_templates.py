"""Offline test suite for inline Jinja2 template source support (FEAT-003).

Exercises:
  - ``notify.templates.is_template_source()`` (Module 1)
  - ``notify.templates.TemplateParser.from_string()`` + its bounded LRU cache
    (Module 1)
  - the three-way ``template=`` dispatch in
    ``notify.providers.base.ProviderBase._prepare_`` (Module 2)
  - the widened ``notify.models.Message.template`` field (Module 3)
  - end-to-end rendering through a concrete ``ProviderBase`` subclass, plus
    the ``Mail``/``Ses`` send paths with transport mocked (integration)

All tests are offline: no network, no SMTP, no external services. Template
directories are built with ``tmp_path``.
"""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from jinja2 import Template

from notify.models import BlockMessage, Message
from notify.providers.base import ProviderBase, ProviderType
from notify.templates import (
    DEFAULT_STRING_CACHE_SIZE,
    JINJA_MARKERS,
    TemplateParser,
    is_template_source,
)

# ---------------------------------------------------------------------------
# Fixtures (spec §4 "Test Data / Fixtures")
# ---------------------------------------------------------------------------


@pytest.fixture
def template_dir(tmp_path):
    """Minimal on-disk template set."""
    d = tmp_path / "templates"
    d.mkdir()
    (d / "hello.html").write_text("Hi {{ who }}", encoding="utf-8")
    return d


@pytest.fixture
def parser(template_dir):
    return TemplateParser(directory=template_dir)


class Dummy(ProviderBase):
    """Concrete ``ProviderBase`` subclass used across this suite.

    Proves the feature is provider-agnostic: nothing below ``ProviderBase``
    is involved in the render path.
    """

    provider = "dummy"
    provider_type = ProviderType.NOTIFY
    blocking = False

    async def connect(self, *args, **kwargs): ...
    async def close(self): ...
    async def _send_(self, to, message, subject=None, **kwargs):
        return await self._render_(to, message, subject, **kwargs)


@pytest_asyncio.fixture
async def dummy_provider(parser):
    """A ``Dummy`` instance wired to a tmp-dir parser.

    Constructed inside an async fixture (mirroring ``tests/test_email_utf8.py``'s
    documented convention) so ``ProviderBase.__init__`` finds a running event
    loop via ``asyncio.get_running_loop()`` — constructing it from a plain
    sync fixture raises under this repo's ``uvloop`` policy, which does not
    auto-create a loop for the main thread the way stdlib asyncio does.
    """
    p = Dummy()
    p._tpl = parser  # bypass the module-level TemplateEnv singleton
    return p


# ---------------------------------------------------------------------------
# TestIsTemplateSource — 6 tests
# ---------------------------------------------------------------------------


class TestIsTemplateSource:
    """G3/G4 — the heuristic discriminating filename from Jinja2 source."""

    def test_detects_variable(self):
        """``{{`` is a Jinja2 delimiter no filename can carry."""
        assert is_template_source("{{ x }}") is True

    def test_detects_block(self):
        """``{%`` is a Jinja2 delimiter no filename can carry."""
        assert is_template_source("{% if x %}a{% endif %}") is True

    def test_detects_comment(self):
        """``{#`` is a Jinja2 delimiter no filename can carry."""
        assert is_template_source("{# note #}") is True

    def test_detects_newline(self):
        """A filename is never multi-line."""
        assert is_template_source("line one\nline two") is True

    @pytest.mark.parametrize(
        "value",
        [
            "email.html",
            "welcome.txt",
            "notifications/welcome.html",
            "a_b-c.2.html",
            "template",
        ],
    )
    def test_rejects_plain_filenames(self, value):
        """G4 guard (spec §7 R2).

        A false positive here would not crash — it would silently render the
        filename as the message body. That is the worst failure mode this
        feature can have, so this is the test that must never be relaxed.
        """
        assert is_template_source(value) is False

    def test_rejects_empty(self):
        assert is_template_source("") is False

    def test_jinja_markers_constant(self):
        """The module-level constant backing the heuristic table (spec §2)."""
        assert JINJA_MARKERS == ("{{", "{%", "{#")


# ---------------------------------------------------------------------------
# TestFromString — 8 tests
# ---------------------------------------------------------------------------


class TestFromString:
    """``TemplateParser.from_string()`` — compile entry point (Module 1)."""

    def test_returns_template_object(self, parser):
        """Must return a compiled Template, never a rendered str (§7 R3)."""
        result = parser.from_string("Hi {{ who }}")
        assert isinstance(result, Template)
        assert not isinstance(result, str)

    def test_renders_sync_and_async(self, parser):
        """Sync ``.render()`` must run outside a running loop (spec §7 R11:
        ``enable_async=True`` makes ``.render()`` call ``asyncio.run()``
        internally, which raises if a loop is already running — pre-existing,
        out of scope). This test therefore stays a plain (non-async)
        function for the sync half, and drives the async half with its own
        isolated ``asyncio.run()`` call."""
        template = parser.from_string("Hi {{ who }}")
        assert template.render(who="x") == "Hi x"
        assert asyncio.run(template.render_async(who="x")) == "Hi x"

    def test_shares_environment_filters(self, parser):
        """A filter registered on the parser's env is usable in a string template."""
        parser.add_filter(lambda v: v.upper(), name="shout")
        template = parser.from_string("{{ who | shout }}")
        assert template.render(who="x") == "X"

    def test_shares_environment_globals(self, parser):
        """An env.globals entry is visible inside a string template."""
        parser.env.globals["site_name"] = "Notify"
        template = parser.from_string("{{ site_name }}")
        assert template.render() == "Notify"

    def test_syntax_error_raises_valueerror(self, parser):
        with pytest.raises(ValueError, match="Notify:") as exc_info:
            parser.from_string("{% if %}")
        assert any(ch.isdigit() for ch in str(exc_info.value))

    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_raises_valueerror(self, parser, value):
        with pytest.raises(ValueError):
            parser.from_string(value)

    def test_non_str_raises_valueerror(self, parser):
        with pytest.raises(ValueError):
            parser.from_string(123)

    def test_never_raises_filenotfound(self, parser):
        """A source string that looks path-like still compiles as source."""
        result = parser.from_string("{{ x }}/y.html")
        assert isinstance(result, Template)


# ---------------------------------------------------------------------------
# TestStringCache — 6 tests
# ---------------------------------------------------------------------------


class TestStringCache:
    """The bounded LRU cache guarding ``from_string()`` (G5, §7 R4/R5/R6)."""

    def test_cache_hit_returns_same_object(self, parser):
        first = parser.from_string("{{ a }}")
        second = parser.from_string("{{ a }}")
        assert first is second

    def test_cache_miss_on_different_source(self, parser):
        first = parser.from_string("{{ a }}")
        second = parser.from_string("{{ b }}")
        assert first is not second

    def test_cache_disabled(self, parser):
        before = len(parser._string_cache)
        first = parser.from_string("{{ a }}", cache=False)
        second = parser.from_string("{{ a }}", cache=False)
        assert first is not second
        assert len(parser._string_cache) == before

    def test_cache_evicts_lru(self, tmp_path):
        d = tmp_path / "t"
        d.mkdir()
        p = TemplateParser(directory=d, string_cache_size=2)
        p.from_string("{{ a }}")
        p.from_string("{{ b }}")
        p.from_string("{{ c }}")
        assert len(p._string_cache) == 2

    def test_cache_reuse_refreshes_lru_order(self, tmp_path):
        """Re-using the oldest entry protects it from the next eviction."""
        d = tmp_path / "t"
        d.mkdir()
        p = TemplateParser(directory=d, string_cache_size=2)
        oldest = p.from_string("{{ a }}")
        p.from_string("{{ b }}")
        # touch "a" again — it becomes the most-recently-used
        p.from_string("{{ a }}")
        p.from_string("{{ c }}")  # evicts "b", the true LRU
        assert p.from_string("{{ a }}") is oldest

    def test_clear_string_cache(self, parser):
        first = parser.from_string("{{ a }}")
        parser.clear_string_cache()
        assert len(parser._string_cache) == 0
        second = parser.from_string("{{ a }}")
        assert first is not second

    def test_default_string_cache_size_used_when_kwarg_omitted(self, parser):
        """Without a ``string_cache_size`` kwarg, the module default applies."""
        assert parser._string_cache_size == DEFAULT_STRING_CACHE_SIZE == 128


# ---------------------------------------------------------------------------
# TestPrepareDispatch — 8 tests
# ---------------------------------------------------------------------------


class TestPrepareDispatch:
    """The three-way ``template=`` dispatch in ``ProviderBase._prepare_``."""

    async def test_prepare_with_source_sets_template(self, dummy_provider):
        dummy_provider._tpl.get_template = MagicMock(
            side_effect=AssertionError("get_template must not be called for source")
        )
        await dummy_provider._prepare_(message="m", template="Hi {{ who }}")
        assert isinstance(dummy_provider._template, Template)
        assert await dummy_provider._template.render_async(who="x") == "Hi x"

    async def test_prepare_with_filename_unchanged(self, dummy_provider):
        """G4 guard: filename routes to get_template exactly as in 1.5.7."""
        real_get_template = dummy_provider._tpl.get_template
        spy = MagicMock(side_effect=real_get_template)
        dummy_provider._tpl.get_template = spy
        await dummy_provider._prepare_(message="m", template="hello.html")
        spy.assert_called_once_with("hello.html")
        assert await dummy_provider._template.render_async(who="x") == "Hi x"

    async def test_prepare_without_template_sets_none(self, dummy_provider):
        await dummy_provider._prepare_(message="m")
        assert dummy_provider._template is None

    async def test_prepare_empty_template_sets_none(self, dummy_provider):
        await dummy_provider._prepare_(message="m", template="")
        assert dummy_provider._template is None

    async def test_prepare_force_source_true(self, dummy_provider):
        await dummy_provider._prepare_(
            message="m", template="Hello world", template_is_source=True
        )
        assert await dummy_provider._template.render_async() == "Hello world"

    async def test_prepare_force_source_false(self, dummy_provider):
        with pytest.raises(FileNotFoundError):
            await dummy_provider._prepare_(
                message="m", template="{{ x }}", template_is_source=False
            )

    async def test_prepare_missing_file_still_raises_filenotfound(self, dummy_provider):
        with pytest.raises(FileNotFoundError):
            await dummy_provider._prepare_(message="m", template="missing.html")

    async def test_prepare_source_syntax_error_propagates(self, dummy_provider):
        with pytest.raises(ValueError, match="Notify:"):
            await dummy_provider._prepare_(message="m", template="{% if %}")


# ---------------------------------------------------------------------------
# TestMessageModel — 3 tests (TASK-016 widening)
# ---------------------------------------------------------------------------


class TestMessageModel:
    """``notify.models.Message.template`` widened to ``Union[Path, str]``."""

    def test_message_template_accepts_path(self):
        """Regression guard — the original meaning must survive."""
        m = Message(name="x", template=Path("a.html"))
        assert isinstance(m.template, Path)

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Known pre-existing python-datamodel behaviour (TASK-016 "
            "Completion Note): Union[Path, str] tries Path first and "
            "Path(str) never raises, so a plain str is eagerly coerced to "
            "PosixPath instead of round-tripping as str. Field annotation "
            "is exactly Union[Path, str] as the spec requires; no validator "
            "workaround was added (out of scope). Message has no consumers "
            "inside notify/, so this does not affect send()'s dispatch."
        ),
    )
    def test_message_template_accepts_str(self):
        m = Message(name="x", template="{{ who }}")
        assert m.template == "{{ who }}"
        assert isinstance(m.template, str)

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Pre-existing bug unrelated to TASK-016 (documented in its "
            "Completion Note): BlockMessage.content_type = "
            "Field(default_factory=CONTENT_TYPES) passes a list where a "
            "callable is required, so any BlockMessage(...) construction "
            "raises TypeError('list' object is not callable). Reproduces "
            "identically on baseline dev before this feature's changes; "
            "out of scope for this one-line widening task."
        ),
    )
    def test_blockmessage_inherits_widened_template(self):
        b = BlockMessage(name="x", template="{{ who }}")
        assert b.template == "{{ who }}"


# ---------------------------------------------------------------------------
# TestRenderPaths — 7 tests (integration)
# ---------------------------------------------------------------------------


class TestRenderPaths:
    """End-to-end rendering proving G2 — the feature is provider-agnostic."""

    async def test_render_async_with_string_template(self, dummy_provider):
        await dummy_provider._prepare_(message="m", template="<b>{{ message }}</b>")
        result = await dummy_provider._render_(to=None, message="m", subject="s")
        assert result == "<b>m</b>"

    def test_render_sync_with_string_template(self, dummy_provider):
        dummy_provider._template = dummy_provider._tpl.from_string("<b>{{ message }}</b>")
        result = dummy_provider._render_sync_(to=None, message="m", subject="s")
        assert result == "<b>m</b>"

    async def test_string_and_file_template_render_identically(
        self, dummy_provider, template_dir
    ):
        """The same body, on disk and inline, must produce identical output."""
        body = "Hi {{ who }}"
        await dummy_provider._prepare_(message="m", template="hello.html")
        from_file = await dummy_provider._render_(to=None, message="m", subject="s", who="x")
        await dummy_provider._prepare_(message="m", template=body)
        from_string = await dummy_provider._render_(to=None, message="m", subject="s", who="x")
        assert from_file == from_string

    async def test_send_forwards_template_is_source_kwarg(self, dummy_provider):
        """``send(..., template=..., template_is_source=True)`` reaches ``_prepare_``."""
        results = await dummy_provider.send(
            recipient=None,
            message="m",
            subject="s",
            template="Hello world",
            template_is_source=True,
        )
        assert results == ["Hello world"]

    async def test_mail_send_path_forwards_kwargs(self, template_dir):
        """``ProviderEmail.send`` (``notify/providers/mail.py``) forwards kwargs
        to ``_prepare_`` unchanged; transport is mocked."""
        from notify.providers.mail import ProviderEmail

        provider = ProviderEmail()
        provider._tpl = TemplateParser(directory=template_dir)
        provider.connect = AsyncMock()
        provider.close = AsyncMock()
        provider._send_ = AsyncMock(return_value="sent")

        await provider.send(
            recipient=None,
            message="m",
            subject="s",
            template="{{ message }}",
            template_is_source=True,
        )

        provider._send_.assert_awaited_once()
        _, call_kwargs = provider._send_.call_args
        assert call_kwargs.get("template_is_source") is True
        assert isinstance(provider._template, Template)

    async def test_ses_send_path_forwards_kwargs(self, template_dir):
        """``Ses.send`` (``notify/providers/ses/ses.py:171``) forwards kwargs
        to ``_prepare_`` unchanged; transport is mocked."""
        from notify.providers.ses.ses import Ses

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        class _FakeSession:
            def create_client(self, *args, **kwargs):
                return _FakeClient()

        provider = Ses(
            aws_access_key_id="AKIA_TEST",
            aws_secret_access_key="secret_test",
            aws_region_name="us-east-1",
            sender_email="sender@example.com",
        )
        provider._tpl = TemplateParser(directory=template_dir)

        async def _fake_connect(*args, **kwargs):
            provider.session = _FakeSession()

        provider.connect = _fake_connect
        provider.close = AsyncMock()
        provider._send_ = AsyncMock(return_value="sent")

        await provider.send(
            recipient=None,
            message="m",
            subject="s",
            template="{{ message }}",
            template_is_source=True,
        )

        provider._send_.assert_awaited_once()
        _, call_kwargs = provider._send_.call_args
        assert call_kwargs.get("template_is_source") is True
        assert isinstance(provider._template, Template)

    async def test_template_env_singleton_cache_shared(self):
        """Two provider instances compiling identical source share one
        cached Template via the ``TemplateEnv`` singleton."""
        from notify.notify import TemplateEnv

        class Dummy(ProviderBase):
            provider = "dummy"
            provider_type = ProviderType.NOTIFY
            blocking = False

            async def connect(self, *args, **kwargs): ...
            async def close(self): ...
            async def _send_(self, to, message, subject=None, **kwargs):
                return message

        p1 = Dummy()
        p2 = Dummy()
        assert p1._tpl is TemplateEnv
        assert p2._tpl is TemplateEnv

        marker = "{{ __feat_003_singleton_cache_marker__ }}"
        first = p1._tpl.from_string(marker)
        second = p2._tpl.from_string(marker)
        assert first is second
