ChangeLog
=========

.. _v2.0.0:

2.0.0 (2026-09-29)
------------------

*Slimmer core install (breaking at install time):*

    The following packages are no longer installed with the base distribution.
    Install the extra that now carries the one you need:

    - ``aiobotocore`` (Amazon SES) -> extra ``ses``
    - ``emoji`` (Telegram) -> extra ``telegram``
    - ``cloudpickle`` (notify server) -> extra ``server``
    - ``pillow`` -> removed entirely; nothing in ``notify`` imported it.

    ``aiohttp`` is now a core dependency (``dialpad``, ``zoom`` and ``teams``
    import it directly and it previously arrived only transitively).

    The ``notify`` console script now requires the ``server`` extra.

    New per-provider extras: ``ses``, ``slack``, ``twilio``, ``xmpp``, plus
    ``server`` for the Redis-backed worker.

*Actionable missing-dependency errors:*

    - A provider whose optional SDK is missing now raises
      ``notify.exceptions.ProviderDependencyError`` naming the missing module and
      the exact extra to install. It subclasses ``ProviderError``, so existing
      ``except ProviderError`` handlers are unaffected.
    - An unknown provider name still raises plain ``ProviderError``, now listing
      the known aliases.

*Fixes:*

    - ``Notify("smtp")`` works. Provider classes are resolved through the
      package's ``__all__`` instead of ``provider.capitalize()``, which asked for
      a non-existent ``Smtp``.

*Faster import:*

    - ``import notify`` no longer pulls in ``jinja2`` or ``datamodel``; both load
      on first template use.
    - **Behaviour change**: ``typing.get_type_hints()`` on ``ProviderBase`` and
      ``ThreadMessage`` methods no longer resolves the ``Actor`` annotation, which
      is now a deferred (``TYPE_CHECKING``) import. If you evaluate those hints at
      runtime, pass it explicitly: ``get_type_hints(fn, localns={"Actor": Actor})``
      with ``Actor`` from ``notify.models``.

*Pure Python — Cython removed:*

    - All Cython extensions (``notify/exceptions.pyx``,
      ``notify/types/typedefs.pyx``) have been migrated to pure Python.
      ``Cython`` is no longer a build dependency.
    - Wheels are now universal (``py3-none-any``) instead of
      platform-specific compiled wheels.
    - The release workflow uses ``uv build`` instead of ``cibuildwheel``.

.. _v0.6.0:

0.6.0 (2022-09-27)
------------------

*New Version:*

    - Upgraded version of Navconfig and AsyncDB.
    - Added support for Datamodels.
    - Security fixes

.. _v0.5.0:

0.5.24 (2022-08-02)
------------------

*New Version:*

    - Fix dependencies from asyncdb and NavConfig
    - Security fixes

0.5.0 (2022-03-02)
------------------

*New Version:*

    - Upgraded to Python +3.9
    - Fix dependencies with asyncdb and NavConfig
    - Changed the Telegram connector to aiogram


.. _v0.4.9:

0.4.9 (2022-03-01)
------------------

*New:*

    - Initial version

.. vim:set ft=rst:
