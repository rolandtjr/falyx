# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""signal_action.py"""
from rich.tree import Tree

from falyx.action.action import Action
from falyx.signals import FlowSignal
from falyx.themes import OneColors


class SignalAction(Action):
    """
    An action that raises a control flow signal when executed.

    Useful for exiting a menu, going back, or halting execution gracefully.
    """

    def __init__(self, name: str, signal: Exception):
        self.signal = signal
        super().__init__(name, action=self.raise_signal)

    async def raise_signal(self, *args, **kwargs):
        raise self.signal

    @property
    def signal(self):
        return self._signal

    @signal.setter
    def signal(self, value: FlowSignal):
        if not isinstance(value, FlowSignal):
            raise TypeError(
                f"Signal must be an FlowSignal instance, got {type(value).__name__}"
            )
        self._signal = value

    def __str__(self):
        return f"SignalAction(name={self.name}, signal={self._signal.__class__.__name__})"

    async def preview(self, parent: Tree | None = None):
        label = f"[{OneColors.LIGHT_RED}]⚡ SignalAction[/] '{self.signal.__class__.__name__}'"
        tree = parent.add(label) if parent else Tree(label)
        if not parent:
            self.console.print(tree)
