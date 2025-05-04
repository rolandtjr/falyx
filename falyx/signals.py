# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
class FlowSignal(BaseException):
    """Base class for all flow control signals in Falyx.

    These are not errors. They're used to control flow like quitting,
    going back, or restarting from user input or nested menus.
    """


class QuitSignal(FlowSignal):
    """Raised to signal an immediate exit from the CLI framework."""

    def __init__(self, message: str = "Quit signal received."):
        super().__init__(message)


class BackSignal(FlowSignal):
    """Raised to return control to the previous menu or caller."""

    def __init__(self, message: str = "Back signal received."):
        super().__init__(message)
