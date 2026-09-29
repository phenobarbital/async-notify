# Copyright (C) 2018-present Jesus Lara
#
"""NotifyException Exceptions."""


class NotifyException(Exception):
    """Base class for other exceptions."""

    code: int = 400

    def __init__(self, message: str, code: int = 0, payload: str = None, **kwargs):
        super().__init__(message)
        self.message = message
        self.args = kwargs
        self.code = int(code)
        self.payload = payload

    def __repr__(self):
        return f"{__name__} -> {self.message}, code: {self.code}"

    def __str__(self):
        return f"{self.message!s}"

    def get(self):
        return self.message


class NotSupported(NotifyException):
    """Not Supported functionality."""


class ProviderError(NotifyException):
    """Provider Error."""


class MessageError(NotifyException):
    """Raises when an error on Message."""


class UninitializedError(ProviderError):
    """Exception when provider cant be initialized."""


class NotifyTimeout(ProviderError):
    """Connection Timeout Error."""


class NotifyAuthError(ProviderError):
    """Notify Authentication error."""


class ProviderDependencyError(ProviderError):
    """Raised when a provider's optional third-party SDK is missing.

    Distinguishes "this provider needs a package you have not installed"
    from "this provider does not exist", which ``ProviderError`` alone
    cannot express. Subclasses :class:`ProviderError`, so existing
    ``except ProviderError`` handlers keep working unchanged.
    """
