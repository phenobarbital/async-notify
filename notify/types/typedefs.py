# Copyright (C) 2018-present Jesus Lara
#
"""Utility types for notify (re-exported for downstream packages)."""


class SafeDict(dict):
    """Allow using partial format strings.

    Missing keys return the key wrapped in braces instead of raising KeyError.
    """

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class AttrDict(dict):
    """Allow using a dictionary like an object."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self

    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class NullDefault(dict):
    """When an attribute is missing, return empty string."""

    def __missing__(self, key):
        return ''


class Singleton(type):
    """Metaclass for Singleton instances."""

    _instances: dict = None

    def __call__(cls, *args, **kwargs):
        if cls._instances is None:
            cls._instances = {}
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


def strtobool(val: str) -> bool:
    """Convert a string representation of truth to True or False.

    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', '0', and 'null'.
    Raises ValueError if val is anything else.
    """
    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return True
    elif val in ('n', 'no', 'f', 'false', 'off', '0', 'null'):
        return False
    else:
        raise ValueError(f"invalid truth value for {val}")
