import importlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
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
    TemplateError,
    TemplateNotFound,
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
            base = JinjaConfig()
            merged = {**base.__dict__, **config}
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
        """add_filter.
        Register a custom function as Template Filter.
        """
        if name is not None:
            filter_name = name
        elif callable(func):
            filter_name = name.__name__
        else:
            raise TypeError(f"Template Filter must be a callable function: {func!r}")
        self.env.filters[filter_name] = func

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
                f"NAV: Error rendering: {filename}, error: {err}"
            ) from err
