# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines all custom exception classes used in the Falyx CLI framework.

These exceptions provide structured error handling for common failure cases,
including command conflicts, invalid actions or hooks, parser errors, and execution guards
like circuit breakers or empty workflows.

All exceptions inherit from `FalyxError`, the base exception for the framework.

Exception Hierarchy:
- FalyxError
    ├── CommandAlreadyExistsError
    ├── InvalidHookError
    ├── InvalidActionError
    ├── NotAFalyxError
    ├── CircuitBreakerOpen
    ├── EmptyChainError
    ├── EmptyGroupError
    ├── EmptyPoolError
    └── CommandArgumentError

These are raised internally throughout the Falyx system to signal user-facing or
developer-facing problems that should be caught and reported.
"""


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
