class notifyException(Exception):
    """Base class for other exceptions."""
    code: int = None
    payload: str = None

    def __init__(self, message: str = None, *args, code: int = None, payload: str = None, **kwargs):
        super(notifyException, self).__init__(*args, **kwargs)
        self.args = (
            message,
            code,
        )
        self.message = message
        if code:
            self.code = code
        if payload:
            self.payload = payload

    def __str__(self):
        return f"{__name__} -> {self.message}"

    def get(self):
        return self.message


class DataError(notifyException, ValueError):
    """An error caused by invalid query input."""


class NotSupported(notifyException):
    """Not Supported functionality."""


class ProviderError(notifyException):
    """Database Provider Error."""


class NotImplementedError(notifyException):
    """Exception for Not implementation."""


class UninitializedError(ProviderError):
    """Exception when provider cant be initialized."""


class ConnectionError(ProviderError):
    """Generic Connection Error."""


class ConnectionTimeout(ProviderError):
    """Connection Timeout Error."""


class TooManyConnections(ProviderError):
    """Too Many Connections."""
