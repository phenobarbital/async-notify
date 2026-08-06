import threading
from collections import OrderedDict
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Optional

from jinja2 import (
    Environment,
    FileSystemLoader,
    Template,
    TemplateError,
    TemplateNotFound,
    TemplateSyntaxError,
)
from navconfig import config
from navconfig.logging import logging

jinja_config = {
    "enable_async": True,
    "extensions": ["jinja2.ext.i18n", "jinja2.ext.loopcontrols"],
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
        directory: Path,
        filters: Optional[list] = None,
        **kwargs
    ):
        self.template = None
        self.path = directory.resolve()
        self.filters = filters
        if not self.path.exists():
            raise RuntimeError(
                f"Notify: template directory {directory} does not exist"
            )
        if "config" in kwargs:
            self.config = {**jinja_config, **kwargs["config"]}
        else:
            self.config = jinja_config
        template_debug = config.getboolean(
            "TEMPLATE_DEBUG", fallback=False
        )
        if template_debug is True:
            self.config["extensions"].append("jinja2.ext.debug")
        # creating loader:
        templateLoader = FileSystemLoader(
            searchpath=[str(self.path)]
        )
        # initialize the environment
        try:
            # TODO: check the bug ,encoding='ANSI'
            self.env: Optional[Environment] = Environment(
                loader=templateLoader, **self.config
            )
            # compiled_path = BytesIO()
            compiled_path = str(
                self.path.joinpath(".compiled")
            )
            self.env.compile_templates(
                target=compiled_path, zip="deflated"
            )
        except Exception as err:
            raise RuntimeError(
                f"Notify: Error loading Template Environment: {err}"
            ) from err
        ### adding custom filters:
        if self.filters is not None:
            self.env.filters.update(self.filters)
        ### string-template cache (G5, R4, R5, R6):
        self.logger = logging.getLogger("Notify.TemplateParser")
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

    def add_filter(self, func: Callable, name: Optional[str] = None) -> None:
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

    def render(self, filename: str, params: Optional[dict] = None) -> str:
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

    async def render_async(self, filename: str, params: Optional[dict] = None) -> str:
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
