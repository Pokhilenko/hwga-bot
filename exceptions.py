"""Custom exceptions for the application."""

class HwgaBotError(Exception):
    """Base class for all application exceptions."""
    pass

class DatabaseError(HwgaBotError):
    """Raised when there is a database error."""
    pass

class DotaApiError(HwgaBotError):
    """Raised when there is an error with the Dota API."""
    pass
