# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Defines all custom exception classes used in the Falyx CLI framework.

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
    ├── CommandArgumentError
    └── EntryNotFoundError

These are raised internally throughout the Falyx system to signal user-facing or
developer-facing problems that should be caught and reported.
"""


class FalyxError(Exception):
    """Base exception class for all Falyx CLI framework errors."""

    def __init__(
        self,
        message: str | None = None,
        hint: str | None = None,
    ):
        if message:
            super().__init__(message)
        self.hint = hint


class CommandAlreadyExistsError(FalyxError):
    """Exception raised when an command with the same key already exists in the Falyx instance."""


class InvalidHookError(FalyxError):
    """Exception raised when a hook is not callable."""


class InvalidActionError(FalyxError):
    """Exception raised when an action is not callable."""


class NotAFalyxError(FalyxError):
    """Exception raised when the provided object is not an instance of a Falyx class."""


class CircuitBreakerOpen(FalyxError):
    """Exception raised when the circuit breaker is open."""


class EmptyChainError(FalyxError):
    """Exception raised when the chain is empty."""


class EmptyGroupError(FalyxError):
    """Exception raised when the group is empty."""


class EmptyPoolError(FalyxError):
    """Exception raised when the pool is empty."""


class UsageError(FalyxError):
    """Exception raised when there is an error in the command usage."""

    def __init__(
        self,
        message: str | None = None,
        hint: str | None = None,
        show_short_usage: bool = True,
    ):
        super().__init__(message, hint)
        self.show_short_usage = show_short_usage


class FalyxOptionError(UsageError):
    """Exception raised when there is an error in the Falyx option parser."""


class CommandArgumentError(UsageError):
    """Exception raised when there is an error in the command argument parser."""


class ArgumentGroupError(CommandArgumentError):
    """Exception raised when there is an error in the argument group."""


class ArgumentParsingError(CommandArgumentError):
    """Exception raised when there is an error during argument parsing."""

    def __init__(
        self,
        message: str | None = None,
        hint: str | None = None,
        show_short_usage: bool = True,
        command_key: str | None = None,
        dest: str | None = None,
        token: str | None = None,
    ):
        self.command_key = command_key
        self.dest = dest
        self.token = token
        super().__init__(message, hint, show_short_usage)


class EntryNotFoundError(UsageError):
    """Exception raised when a routing entry is not found."""

    def __init__(
        self,
        unknown_name: str,
        suggestions: list[str] | None = None,
        message_context: str = "",
        show_short_usage: bool = True,
    ):
        self.unknown_name = unknown_name
        self.suggestions = suggestions
        self.message_context = message_context
        super().__init__(
            self.build_message(),
            self.build_hint(),
            show_short_usage,
        )

    def build_message(self) -> str:
        prefix = f"{self.message_context}: " if self.message_context else ""
        return f"{prefix}unknown command or namespace '{self.unknown_name}'."

    def build_hint(self) -> str | None:
        if self.suggestions:
            return f"did you mean: {', '.join(self.suggestions[:10])}?"
        else:
            return None


class UnrecognizedOptionError(ArgumentParsingError):
    def __init__(
        self,
        token: str,
        remaining_flags: list[str] | None = None,
        show_short_usage: bool = True,
    ):
        self.remaining_flags = remaining_flags
        self.token = token
        super().__init__(
            self.build_message(),
            self.build_hint(),
            show_short_usage=show_short_usage,
            token=token,
        )

    def build_message(self) -> str:
        return f"unrecognized option '{self.token}'"

    def build_hint(self) -> str:
        if self.remaining_flags:
            return f"did you mean one of: {', '.join(self.remaining_flags)}?"
        return "use --help to see available options"


class InvalidValueError(ArgumentParsingError):
    def __init__(
        self,
        dest: str | None = None,
        choices: list[str] | None = None,
        expected: str | None = None,
        error: Exception | str | None = None,
        show_short_usage: bool = True,
    ):
        self.choices = choices
        self.expected = expected
        self.error = error
        self.dest = dest
        super().__init__(
            self.build_message(),
            self.build_hint(),
            show_short_usage=show_short_usage,
            dest=dest,
        )

    def build_message(self) -> str:
        if self.dest and self.choices:
            return f"invalid value for '{self.dest}'"
        elif self.dest and self.error:
            return f"invalid value for '{self.dest}': {self.error}"
        elif self.dest and self.expected:
            return f"invalid value for '{self.dest}': expected {self.expected}"
        else:
            return "invalid command argument value."

    def build_hint(self) -> str | None:
        if self.dest and self.choices:
            return f"the value for '{self.dest}' must be one of {{{', '.join(self.choices)}}}."
        else:
            return None


class MissingValueError(ArgumentParsingError):
    def __init__(
        self,
        dest: str,
        expected_count: int | None = None,
        actual_count: int | None = None,
    ):
        self.expected_count = expected_count
        self.actual_count = actual_count
        self.dest = dest


class TokenizationError(UsageError):
    raw_input: str | None = None
