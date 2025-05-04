from falyx.action import Action
from falyx.signals import FlowSignal


class SignalAction(Action):
    """
    An action that raises a control flow signal when executed.

    Useful for exiting a menu, going back, or halting execution gracefully.
    """

    def __init__(self, name: str, signal: Exception):
        if not isinstance(signal, FlowSignal):
            raise TypeError(
                f"Signal must be an FlowSignal instance, got {type(signal).__name__}"
            )

        async def raise_signal(*args, **kwargs):
            raise signal

        super().__init__(name=name, action=raise_signal)
        self._signal = signal

    @property
    def signal(self):
        return self._signal

    def __str__(self):
        return f"SignalAction(name={self.name}, signal={self._signal.__class__.__name__})"
