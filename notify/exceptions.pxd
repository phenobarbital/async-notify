# cython: language_level=3, embedsignature=True, boundscheck=False, wraparound=True, initializedcheck=False
# Copyright (C) 2018-present Jesus Lara
#
"""NotifyException Exceptions."""
cdef class NotifyException(Exception):
    """Base class for other exceptions"""

## Other Errors:
cdef class NotSupported(NotifyException):
    """Not Supported functionality."""
    pass

cdef class ProviderError(NotifyException):
    """Database Provider Error."""
    pass

cdef class MessageError(NotifyException):
    """Raises when an error on Message."""
    pass

cdef class UninitializedError(ProviderError):
    """Exception when provider cant be initialized."""
    pass

cdef class NotifyTimeout(ProviderError):
    """Connection Timeout Error."""
    pass
