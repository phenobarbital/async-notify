"""Lightweight template helpers.

Deliberately free of jinja2, datamodel and navconfig imports: this module sits
on the ``import notify`` startup path via :mod:`notify.providers.base`, and
pulling any of those three back in undoes FEAT-005's G6 deferral.
"""

from __future__ import annotations

#: Jinja2 delimiters that can never appear in a template *filename*.
JINJA_MARKERS: tuple[str, ...] = ("{{", "{%", "{#")


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
