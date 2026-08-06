Api Reference
==============


``commands``
--------------



``exceptions``
--------------



``extensions``
--------------



``libs``
--------------


``templates``
--------------

``notify.templates`` wraps the Jinja2 template engine used to render message
bodies. As of ``1.6.0`` it can compile a template from a **filename** on
``TEMPLATE_DIR`` (the original behaviour) or from raw Jinja2 **source text**
supplied at call time — see ``providers.rst`` ("Template Support") for the
``send(template=...)`` overload that consumes this.

``is_template_source(value)``
    Module-level heuristic deciding whether *value* is Jinja2 source rather
    than a filename. Returns ``True`` only when *value* contains a Jinja2
    delimiter (``{{``, ``{%``, ``{#``) or a line break — anything else,
    including every realistic template filename, is ``False``.

``TemplateParser.from_string(source, *, cache=True)``
    Compiles Jinja2 *source* text into a ``jinja2.Template`` on the parser's
    own ``Environment``, so a string template sees the same filters, globals,
    extensions and ``enable_async`` setting as a file template. When
    ``cache`` is ``True`` (the default), the compiled template is memoised in
    a bounded LRU keyed by the SHA-256 of *source*; pass ``cache=False`` for
    a genuinely one-shot body. Raises ``ValueError`` for empty/blank/non-``str``
    input or a Jinja2 syntax error (the message carries ``"Notify:"`` and the
    offending line number), and ``RuntimeError`` for any other compilation
    failure. It never raises ``FileNotFoundError`` — that is reserved for the
    filename path.

``TemplateParser.clear_string_cache()``
    Empties the compiled-string-template cache.

``string_cache_size`` (constructor keyword)
    Upper bound on the number of compiled string templates the LRU cache
    retains, default ``128`` (``notify.templates.DEFAULT_STRING_CACHE_SIZE``).
    Least-recently-used entries are evicted once the bound is exceeded.

Example::

    from notify.templates import TemplateParser, is_template_source

    parser = TemplateParser(directory=TEMPLATE_DIR, string_cache_size=256)

    is_template_source("welcome.html")        # False -> a filename
    is_template_source("Hi {{ name }}")        # True  -> Jinja2 source

    template = parser.from_string("Hi {{ name }}")
    await template.render_async(name="Ada")    # "Hi Ada"

``notify.models.Message.template``
    As of ``1.6.0``, ``Message.template`` (inherited by ``BlockMessage`` and
    ``MailMessage``) is typed ``Union[Path, str]`` instead of ``Path``, so the
    model can carry either a template filename or inline Jinja2 source,
    matching the widened ``send(template=...)`` semantics above.
    ``notify.models.Message`` has no consumers inside ``notify/`` itself —
    ``send()`` reads the ``template=`` keyword argument directly, never
    ``Message.template`` — so this widening only matters to code that
    constructs a ``Message`` directly. **Known caveat**: the underlying
    ``python-datamodel`` library resolves ``Union`` members in declaration
    order and tries ``Path`` first; since ``Path(some_str)`` never raises, a
    plain ``str`` assigned to ``template`` is currently coerced to
    ``PosixPath`` rather than round-tripping as ``str``. This is a
    ``python-datamodel`` behaviour, not something ``Message`` opts out of.

