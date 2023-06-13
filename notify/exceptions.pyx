# cython: language_level=3, embedsignature=True, boundscheck=False, wraparound=True, initializedcheck=False
# Copyright (C) 2018-present Jesus Lara
#
"""NotifyException Exceptions."""
cdef class NotifyException(Exception):
    """Base class for other exceptions"""

    code: int = 400

    def __init__(self, str message, int code = 0, str payload = None, **kwargs):
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

cdef class NotSupported(NotifyException):
    """Not Supported functionality."""


cdef class ProviderError(NotifyException):
    """Database Provider Error."""


cdef class MessageError(NotifyException):
    """Raises when an error on Message."""


cdef class UninitializedError(ProviderError):
    """Exception when provider cant be initialized."""


cdef class NotifyTimeout(ProviderError):
    """Connection Timeout Error."""
