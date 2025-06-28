# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""exceptions.py"""


class FalyxError(Exception):
    """Custom exception for the Menu class."""


class CommandAlreadyExistsError(FalyxError):
    """Exception raised when an command with the same key already exists in the menu."""


class InvalidHookError(FalyxError):
    """Exception raised when a hook is not callable."""


class InvalidActionError(FalyxError):
    """Exception raised when an action is not callable."""


class NotAFalyxError(FalyxError):
    """Exception raised when the provided submenu is not an instance of Menu."""


class CircuitBreakerOpen(FalyxError):
    """Exception raised when the circuit breaker is open."""


class EmptyChainError(FalyxError):
    """Exception raised when the chain is empty."""


class EmptyGroupError(FalyxError):
    """Exception raised when the chain is empty."""


class EmptyPoolError(FalyxError):
    """Exception raised when the chain is empty."""


class CommandArgumentError(FalyxError):
    """Exception raised when there is an error in the command argument parser."""
