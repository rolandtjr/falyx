# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines flow control signals used internally by the Falyx CLI framework.

These signals are raised to interrupt or redirect CLI execution flow
(e.g., returning to a menu, quitting, or displaying help) without
being treated as traditional exceptions.

All signals inherit from `FlowSignal`, which is a subclass of `BaseException`
to ensure they bypass standard `except Exception` blocks.

Signals:
- BreakChainSignal: Exit a chained action early.
- QuitSignal: Terminate the CLI session.
- BackSignal: Return to the previous menu or caller.
- CancelSignal: Cancel the current operation.
- HelpSignal: Trigger help output in interactive flows.
"""


class FlowSignal(BaseException):
    """Base class for all flow control signals in Falyx.

    These are not errors. They're used to control flow like quitting,
    going back, or restarting from user input or nested menus.
    """


class BreakChainSignal(FlowSignal):
    """Raised to break the current action chain and return to the previous context."""

    def __init__(self, message: str = "Break chain signal received."):
        super().__init__(message)


class QuitSignal(FlowSignal):
    """Raised to signal an immediate exit from the CLI framework."""

    def __init__(self, message: str = "Quit signal received."):
        super().__init__(message)


class BackSignal(FlowSignal):
    """Raised to return control to the previous menu or caller."""

    def __init__(self, message: str = "Back signal received."):
        super().__init__(message)


class CancelSignal(FlowSignal):
    """Raised to cancel the current command or action."""

    def __init__(self, message: str = "Cancel signal received."):
        super().__init__(message)


class HelpSignal(FlowSignal):
    """Raised to display help information."""

    def __init__(self, message: str = "Help signal received."):
        super().__init__(message)
