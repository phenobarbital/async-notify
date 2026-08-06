import importlib
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from dataclasses import fields as dataclass_fields
from hashlib import sha256
from pathlib import Path
from typing import Any

from jinja2 import (
    BaseLoader,
    ChoiceLoader,
    DictLoader,
    Environment,
    FileSystemBytecodeCache,
    FileSystemLoader,
    StrictUndefined,
    Template,
    TemplateError,
    TemplateNotFound,
    TemplateSyntaxError,
    Undefined,
)
from navconfig import config as nav_config
from navconfig.logging import logging

PathLike = str | Path


@dataclass
class JinjaConfig:
    """Configuration for the Jinja2 Environment behind TemplateParser.

    Every default reproduces async-notify's behaviour as of 1.5.7.

    Attributes:
        template_dirs: Ordered list of on-disk template directories.
        extensions: Jinja2 extensions loaded unconditionally.
        optional_extensions: Third-party extensions loaded tolerantly
            (missing packages are skipped with a warning).
        enable_async: Whether the Jinja2 Environment supports
            ``render_async``. Unchanged from the legacy ``jinja_config``.
        autoescape: Jinja2 ``autoescape`` setting. Opt-in only; defaults to
            ``False`` to preserve today's effective behaviour.
        undefined: Jinja2 ``Undefined`` class. Defaults to the permissive
            ``jinja2.Undefined``.
        trim_blocks: Jinja2 ``trim_blocks`` setting. Defaults to ``False``
            (Jinja2's own default, NOT ai-parrot's ``True``).
        lstrip_blocks: Jinja2 ``lstrip_blocks`` setting. Defaults to
            ``False`` (Jinja2's own default, NOT ai-parrot's ``True``).
        keep_trailing_newline: Jinja2 ``keep_trailing_newline`` setting.
            Defaults to ``False`` (Jinja2's own default, NOT ai-parrot's
            ``True``).
        bytecode_cache_dir: Optional directory backing a
            ``FileSystemBytecodeCache``. When ``None``, no bytecode cache
            is wired.
        bytecode_cache_pattern: Filename pattern for the bytecode cache.
    """
    template_dirs: list[Path] = field(default_factory=list)
    extensions: list[str] = field(default_factory=lambda: [
        "jinja2.ext.i18n",
        "jinja2.ext.loopcontrols",
        "jinja2.ext.do",
    ])
    optional_extensions: list[str] = field(default_factory=lambda: [
        "jinja2_time.TimeExtension",
        "jinja2_iso8601.ISO8601Extension",
        "jinja2_humanize_extension.HumanizeExtension",
    ])
    enable_async: bool = True
    autoescape: Any = False
    undefined: Any = Undefined
    trim_blocks: bool = False
    lstrip_blocks: bool = False
    keep_trailing_newline: bool = False
    bytecode_cache_dir: Path | None = None
    bytecode_cache_pattern: str = "%s.cache"


# Deprecated module-level alias, kept for backward compatibility:
# `from notify.templates import jinja_config` keeps working.
jinja_config = {
    "enable_async": JinjaConfig().enable_async,
    "extensions": list(JinjaConfig().extensions),
}

#: Jinja2 delimiters that can never appear in a template *filename*.
JINJA_MARKERS: tuple[str, ...] = ("{{", "{%", "{#")

#: Default upper bound on the number of compiled string templates retained.
DEFAULT_STRING_CACHE_SIZE: int = 128


def is_template_source(value: str) -> bool:
    """Decide whether *value* is Jinja2 source text rather than a filename.

    Conservative by design: returns ``True`` only when *value* carries a
    signal that a template filename cannot carry — a Jinja2 delimiter
    (``{{``, ``{%``, ``{#``) or a line break. Anything else is treated as a
    filename, which preserves 1.5.7 behaviour for every existing caller.

    Args:
        value: The raw ``template=`` argument.

    Returns:
        ``True`` if *value* should be compiled as source, ``False`` if it
        should be resolved through the filesystem loader.
    """
    if not isinstance(value, str) or not value:
        return False
    if any(marker in value for marker in JINJA_MARKERS):
        return True
    return "\n" in value or "\r" in value


class TemplateParser:
    """
    TemplateParser.

    This is a wrapper for the Jinja2 template engine.
    """

    def __init__(
        self,
        directory: PathLike | None = None,
        filters: list | Mapping[str, Callable] | None = None,
        *,
        template_dirs: Sequence[PathLike] | None = None,
        globals_: Mapping[str, Any] | None = None,
        config: "JinjaConfig | dict | None" = None,
        bytecode_cache_dir: PathLike | None = None,
        autoescape: bool | Callable | None = None,
        strict_undefined: bool = False,
        strict_directory: bool = False,
        **kwargs
    ):
        """Construct a TemplateParser wrapping a Jinja2 Environment.

        Args:
            directory: Legacy first positional template directory. Accepts
                both ``str`` and ``Path`` and is now optional.
            filters: Either a mapping of ``{name: callable}`` (applied
                directly) or a sequence of callables registered by
                ``func.__name__``.
            template_dirs: Additional template directories layered after
                ``directory``, searched in order (first match wins).
            globals_: Mapping of global variables/functions exposed to
                every template.
            config: A :class:`JinjaConfig` instance (copied, never mutated)
                or a legacy ``dict`` shallow-merged over the defaults.
            bytecode_cache_dir: When given, wires a
                ``jinja2.FileSystemBytecodeCache`` rooted at this directory
                (created if absent).
            autoescape: Overrides ``JinjaConfig.autoescape`` for this
                instance.
            strict_undefined: When ``True``, uses ``jinja2.StrictUndefined``
                instead of the permissive default.
            strict_directory: When ``True``, restores the legacy
                ``RuntimeError`` if a template directory is missing instead
                of degrading to a warning + memory-only mode.
            **kwargs: Reserved for forward compatibility; unused today.

        Raises:
            RuntimeError: If a template directory is missing and
                ``strict_directory=True``, or if the Jinja2 Environment
                fails to construct.
        """
        self.logger = logging.getLogger("notify.templates")
        self.template = None
        self.filters = filters

        # --- Resolve JinjaConfig (dataclass instance, dict, or defaults) ---
        # Legacy dict callers may pass arbitrary jinja2.Environment kwargs
        # (e.g. variable_start_string=) that are not JinjaConfig fields.
        # Pre-refactor (templates.py:33-36) these were shallow-merged and
        # splatted straight into Environment(**self.config) — preserve that
        # by routing anything outside JinjaConfig's field set straight
        # through to the Environment() call at the end of __init__, instead
        # of rejecting it.
        extra_env_kwargs: dict[str, Any] = {}
        if isinstance(config, JinjaConfig):
            # Never mutate a caller-supplied JinjaConfig (spec §7 R7):
            # deep-copy its mutable fields before touching anything.
            cfg = JinjaConfig(
                template_dirs=list(config.template_dirs),
                extensions=list(config.extensions),
                optional_extensions=list(config.optional_extensions),
                enable_async=config.enable_async,
                autoescape=config.autoescape,
                undefined=config.undefined,
                trim_blocks=config.trim_blocks,
                lstrip_blocks=config.lstrip_blocks,
                keep_trailing_newline=config.keep_trailing_newline,
                bytecode_cache_dir=config.bytecode_cache_dir,
                bytecode_cache_pattern=config.bytecode_cache_pattern,
            )
        elif isinstance(config, dict):
            # Legacy behaviour (templates.py:33-36 pre-refactor): shallow
            # merge over the defaults.
            known_fields = {f.name for f in dataclass_fields(JinjaConfig)}
            known_overrides = {k: v for k, v in config.items() if k in known_fields}
            extra_env_kwargs = {k: v for k, v in config.items() if k not in known_fields}
            base = JinjaConfig()
            merged = {**base.__dict__, **known_overrides}
            cfg = JinjaConfig(**merged)
        else:
            cfg = JinjaConfig()

        # --- Resolve directories: legacy `directory=` + new `template_dirs=` ---
        dirs: list[Path] = list(cfg.template_dirs)
        if directory is not None:
            dirs.append(Path(directory).resolve())
        if template_dirs:
            dirs.extend(Path(d).resolve() for d in template_dirs)

        missing_dirs = [d for d in dirs if not d.exists()]
        if missing_dirs:
            if strict_directory:
                raise RuntimeError(
                    f"Notify: template directory {missing_dirs[0]} does not exist"
                )
            self.logger.warning(
                "Notify: template director%s %s not found; "
                "continuing in memory-only mode for %s.",
                "y" if len(missing_dirs) == 1 else "ies",
                missing_dirs,
                missing_dirs,
            )
            dirs = [d for d in dirs if d.exists()]

        self.path = dirs[0] if dirs else None
        # Filesystem directories backing the loader, kept so
        # add_template_dir() can extend the FileSystemLoader at runtime
        # without losing previously registered directories.
        self._fs_dirs: list[Path] = dirs

        ### legacy TEMPLATE_DEBUG handling — per-instance list, no shared leak.
        template_debug = nav_config.getboolean(
            "TEMPLATE_DEBUG", fallback=False
        )
        extensions = list(cfg.extensions)
        if template_debug is True:
            extensions.append("jinja2.ext.debug")

        # --- Tolerant optional-extension loading (spec §7 R8) ---
        for dotted in cfg.optional_extensions:
            module_name = dotted.rsplit(".", 1)[0]
            try:
                importlib.import_module(module_name)
            except ImportError:
                self.logger.warning(
                    "Notify: optional Jinja2 extension %s unavailable; "
                    "skipping. Install the 'templates' extra to enable it.",
                    dotted,
                )
                continue
            extensions.append(dotted)

        # --- Layered loader: in-memory templates shadow the filesystem ---
        self._dict_loader = DictLoader({})
        loaders: list[BaseLoader] = [self._dict_loader]
        if dirs:
            loaders.append(FileSystemLoader(searchpath=[str(d) for d in dirs]))
        self._choice_loader = ChoiceLoader(loaders)

        # --- Resolve autoescape / undefined overrides ---
        effective_autoescape = autoescape if autoescape is not None else cfg.autoescape
        effective_undefined = StrictUndefined if strict_undefined else cfg.undefined

        # --- Optional bytecode cache (opt-in; replaces compile_templates()) ---
        cache_dir = bytecode_cache_dir or cfg.bytecode_cache_dir
        bytecode_cache = None
        if cache_dir is not None:
            cache_dir = Path(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            bytecode_cache = FileSystemBytecodeCache(
                directory=str(cache_dir), pattern=cfg.bytecode_cache_pattern
            )

        self.config = {
            "enable_async": cfg.enable_async,
            "extensions": extensions,
            "autoescape": effective_autoescape,
            "undefined": effective_undefined,
            "trim_blocks": cfg.trim_blocks,
            "lstrip_blocks": cfg.lstrip_blocks,
            "keep_trailing_newline": cfg.keep_trailing_newline,
            **extra_env_kwargs,
        }
        # initialize the environment
        try:
            self.env: Environment | None = Environment(
                loader=self._choice_loader,
                bytecode_cache=bytecode_cache,
                **self.config,
            )
        except Exception as err:
            raise RuntimeError(
                f"Notify: Error loading Template Environment: {err}"
            ) from err

        ### adding custom filters:
        if self.filters is not None:
            if isinstance(self.filters, Mapping):
                self.env.filters.update(self.filters)
            else:
                for func in self.filters:
                    self.env.filters[func.__name__] = func

        ### adding globals:
        if globals_:
            self.env.globals.update(globals_)

        ### string-template cache (G5, R4, R5, R6):
        self._string_cache: OrderedDict[str, Template] = OrderedDict()
        self._string_cache_size: int = kwargs.get(
            "string_cache_size", DEFAULT_STRING_CACHE_SIZE
        )
        self._string_cache_lock = threading.Lock()

    def _compile_source(self, source: str) -> Template:
        """Compile Jinja2 *source* text into a Template, mapping errors.

        Args:
            source: Jinja2 template source text.

        Returns:
            A compiled :class:`jinja2.Template`.

        Raises:
            ValueError: If *source* fails to parse (``TemplateSyntaxError``).
            RuntimeError: On any other compilation failure.
        """
        try:
            return self.env.from_string(source)
        except TemplateSyntaxError as ex:
            raise ValueError(
                f"Notify: Error parsing template source at line {ex.lineno}: {ex.message}"
            ) from ex
        except Exception as err:
            raise RuntimeError(
                f"Notify: Error compiling template source: {err}"
            ) from err

    def from_string(self, source: str, *, cache: bool = True) -> Template:
        """Compile Jinja2 *source* text into a Template on this Environment.

        The returned template shares the parser's filters, globals,
        extensions and ``enable_async`` setting, so it renders identically
        to an equivalent on-disk template.

        Args:
            source: Jinja2 template source text.
            cache: When ``True`` (default), memoise the compiled template in
                a bounded LRU keyed by the SHA-256 of *source*.

        Returns:
            A compiled :class:`jinja2.Template`.

        Raises:
            ValueError: If *source* is empty/blank, is not a ``str``, or
                fails to parse (``jinja2.TemplateSyntaxError``). The message
                carries the offending line number.
            RuntimeError: On any other compilation failure.
        """
        if not isinstance(source, str) or not source.strip():
            raise ValueError(
                f"Notify: template source must be a non-empty string, got {source!r}"
            )
        if not cache:
            return self._compile_source(source)
        key = sha256(source.encode("utf-8")).hexdigest()
        with self._string_cache_lock:
            if key in self._string_cache:
                self._string_cache.move_to_end(key)
                return self._string_cache[key]
        template = self._compile_source(source)
        with self._string_cache_lock:
            self._string_cache[key] = template
            self._string_cache.move_to_end(key)
            while len(self._string_cache) > self._string_cache_size:
                evicted, _ = self._string_cache.popitem(last=False)
                self.logger.debug(f"Evicted string template {evicted[:12]} from cache")
        return template

    def clear_string_cache(self) -> None:
        """Drop every compiled string template from the LRU cache."""
        with self._string_cache_lock:
            self._string_cache.clear()

    def get_template(self, filename: str):
        """
        Get a template from Template Environment using the Filename.
        """
        try:
            self.template = self.env.get_template(str(filename))
            return self.template
        except TemplateNotFound as ex:
            raise FileNotFoundError(
                f"Template cannot be found: {filename}"
            ) from ex
        except Exception as ex:
            raise RuntimeError(
                f"Error parsing Template {filename}: {ex}"
            ) from ex

    @property
    def environment(self):
        return self.env

    def add_filter(self, func: Callable, name: str | None = None) -> None:
        """Register a single callable as a Jinja2 template filter.

        Args:
            func: The callable to register.
            name: Filter name. Defaults to ``func.__name__``.

        Raises:
            TypeError: If ``func`` is not callable.
        """
        if not callable(func):
            raise TypeError(
                f"Notify: Template Filter must be a callable function: {func!r}"
            )
        self.add_filters({name or func.__name__: func})

    def render(self, filename: str, params: dict | None = None) -> str:
        if not params:
            params = {}
        result = None
        try:
            self.template = self.env.get_template(str(filename))
            result = self.template.render(**params)
            return result
        except Exception as err:
            raise RuntimeError(
                f"Notify: Error rendering template: {filename}, error: {err}"
            ) from err

    async def render_async(self, filename: str, params: dict | None = None) -> str:
        """Render.
        Renders a Jinja2 template using async-await syntax.
        """
        result = None
        if not params:
            params = {}
        try:
            template = self.env.get_template(str(filename))
            result = await template.render_async(**params)
            return result
        except TemplateError as ex:
            raise ValueError(
                f"Template parsing error, template: {filename}: {ex}"
            ) from ex
        except Exception as err:
            raise RuntimeError(
                f"Notify: Error rendering: {filename}, error: {err}"
            ) from err

    def add_template_dir(self, path: PathLike) -> None:
        """Add a filesystem directory to the search path at runtime.

        Rebuilds the internal ``ChoiceLoader``, carrying the existing
        in-memory template mapping across so templates registered via
        :meth:`add_templates` are not lost (spec §7 R6).

        Args:
            path: Directory to add. Must exist and be a directory.

        Raises:
            ValueError: If the path does not exist or is not a directory.
        """
        p = Path(path).resolve()
        if not p.exists() or not p.is_dir():
            raise ValueError(f"Notify: template directory invalid: {p}")
        self._fs_dirs.append(p)
        if self.path is None:
            self.path = p
        # Rebuild the chain — carry the EXISTING in-memory mapping across.
        mapping = self._dict_loader.mapping
        self._dict_loader = DictLoader(mapping)
        self._choice_loader = ChoiceLoader([
            self._dict_loader,
            FileSystemLoader([str(d) for d in self._fs_dirs]),
        ])
        self.env.loader = self._choice_loader
        # A name already resolved (and cached) from an earlier directory
        # must not keep winning over a template newly reachable through
        # this one — same cache-invalidation rationale as add_templates().
        if self.env.cache is not None:
            self.env.cache.clear()

    def add_templates(self, templates: Mapping[str, str]) -> None:
        """Register or override in-memory templates.

        In-memory templates shadow filesystem templates of the same name,
        since the ``DictLoader`` is searched first in the ``ChoiceLoader``.

        Args:
            templates: Mapping of template name to template source.
        """
        self._dict_loader.mapping.update(templates)
        # jinja2.Environment.get_template() consults its own template
        # cache before the loader chain. Without invalidating it, a name
        # already rendered from the filesystem keeps winning over an
        # in-memory override registered afterwards — clear it so the
        # shadowing guarantee above actually holds for already-cached names.
        if self.env.cache is not None:
            self.env.cache.clear()

    def add_filters(self, filters: Mapping[str, Callable]) -> None:
        """Bulk-register custom template filters.

        Args:
            filters: Mapping of filter name to callable.
        """
        self.env.filters.update(filters)

    def add_globals(self, globals_: Mapping[str, Any]) -> None:
        """Register global variables/functions visible to every template.

        Args:
            globals_: Mapping of global name to value or callable.
        """
        self.env.globals.update(globals_)

    def render_string(self, source: str, params: dict | None = None) -> str:
        """Render ad-hoc template source synchronously.

        Mirrors :meth:`render`, but takes raw template source instead of a
        filename — stays synchronous, unlike ai-parrot's async-only
        ``render_string`` (spec §1 Non-Goals).

        Args:
            source: Raw Jinja2 template source.
            params: Template rendering context.

        Returns:
            The rendered string.
        """
        if not params:
            params = {}
        try:
            template = self.env.from_string(source)
            return template.render(**params)
        except TemplateError as ex:
            raise ValueError(
                f"Template parsing error rendering inline source: {ex}"
            ) from ex
        except Exception as err:
            raise RuntimeError(
                f"Notify: Error rendering inline source: {err}"
            ) from err

    async def render_string_async(self, source: str, params: dict | None = None) -> str:
        """Render ad-hoc template source asynchronously.

        Args:
            source: Raw Jinja2 template source.
            params: Template rendering context.

        Returns:
            The rendered string.
        """
        if not params:
            params = {}
        try:
            template = self.env.from_string(source)
            return await template.render_async(**params)
        except TemplateError as ex:
            raise ValueError(
                f"Template parsing error rendering inline source: {ex}"
            ) from ex
        except Exception as err:
            raise RuntimeError(
                f"Notify: Error rendering inline source: {err}"
            ) from err

    def compile_directory(self, target: PathLike, *, zip: str | None = "deflated") -> None:
        """Explicitly compile templates to bytecode.

        Replaces the unconditional ``compile_templates()`` call removed
        from ``__init__`` (spec §7 R3) with an opt-in, explicit call. No-op
        when there are no filesystem directories to compile.

        Args:
            target: Destination directory (or zip file) for compiled
                templates, passed straight to
                ``jinja2.Environment.compile_templates``.
            zip: Compression mode forwarded to
                ``jinja2.Environment.compile_templates``.
        """
        if not self._fs_dirs:
            return
        self.env.compile_templates(target=str(target), zip=zip)
