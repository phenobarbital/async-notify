.. async-notify documentation master file, created by
   sphinx-quickstart on Fri Sep 16 07:35:11 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to async-notify's documentation!
============================================


.. image:: https://img.shields.io/pypi/v/async-notify
   :target: https://pypi.org/project/async-notify/
   :alt: PyPI
.. image:: https://github.com/phenobarbital/async-notify/workflows/CI/badge.svg
   :target: https://github.com/phenobarbital/async-notify/actions?query=workflow%3ACI
   :alt: GitHub Actions - CI
.. image:: https://github.com/phenobarbital/async-notify/workflows/pre-commit/badge.svg
   :target: https://github.com/phenobarbital/async-notify/actions?query=workflow%3Apre-commit
   :alt: GitHub Actions - pre-commit
.. image:: https://img.shields.io/codecov/c/gh/phenobarbital/async-notify
   :target: https://app.codecov.io/gh/phenobarbital/async-notify
   :alt: Codecov


.. include:: ../README.md
   :parser: myst_parser.sphinx_


Quick Start
----------

Installation
~~~~~~~~~~

.. code-block:: bash

    pip install async-notify

Basic Usage
~~~~~~~~~

.. code-block:: python

    from notify import Notify

    # Create a notification provider
    email = Notify(
        "email",
        username="user@example.com",
        password="secret"
    )

    # Send a notification
    await email.send(
        recipient=["user@example.com"],
        subject="Hello",
        message="Hello from async-notify!"
    )

Features
-------

- Multiple notification providers (email, SMS, chat, push)
- Async/await interface
- Template support
- File attachments
- Rich message formatting
- Error handling and retries
- Connection pooling
- Server components for queuing and persistence

License
-------

This project is licensed under the terms of the BSD v3. and Apache 2 Dual license.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   architecture
   models
   providers
   examples
   server
   api
   authors

Indices and tables
==================


* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`