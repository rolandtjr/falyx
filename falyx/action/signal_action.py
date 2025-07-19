# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines `SignalAction`, a lightweight Falyx Action that raises a `FlowSignal`
(such as `BackSignal`, `QuitSignal`, or `BreakChainSignal`) during execution to
alter or exit the CLI flow.

Unlike traditional actions, `SignalAction` does not return a result—instead, it raises
a signal to break, back out, or exit gracefully. Despite its minimal behavior,
it fully supports Falyx's hook lifecycle, including `before`, `on_error`, `after`,
and `on_teardown`—allowing it to trigger logging, audit events, UI updates, or custom
telemetry before halting flow.

Key Features:
- Declaratively raises a `FlowSignal` from within any Falyx workflow
- Works in menus, chained actions, or conditionals
- Hook-compatible: can run pre- and post-signal lifecycle hooks
- Supports previewing and structured introspection

Use Cases:
- Implementing "Back", "Cancel", or "Quit" options in `MenuAction` or `PromptMenuAction`
- Triggering an intentional early exit from a `ChainedAction`
- Running cleanup hooks before stopping execution

Example:
    SignalAction("ExitApp", QuitSignal(), hooks=my_hook_manager)
"""
from rich.tree import Tree

from falyx.action.action import Action
from falyx.hook_manager import HookManager
from falyx.signals import FlowSignal
from falyx.themes import OneColors


class SignalAction(Action):
    """
    A hook-compatible action that raises a control flow signal when invoked.

    `SignalAction` raises a `FlowSignal` (e.g., `BackSignal`, `QuitSignal`,
    `BreakChainSignal`) during execution. It is commonly used to exit menus,
    break from chained actions, or halt workflows intentionally.

    Even though the signal interrupts normal flow, all registered lifecycle hooks
    (`before`, `on_error`, `after`, `on_teardown`) are triggered as expected—
    allowing structured behavior such as logging, analytics, or UI changes
    before the signal is raised.

    Args:
        name (str): Name of the action (used for logging and debugging).
        signal (FlowSignal): A subclass of `FlowSignal` to raise (e.g., QuitSignal).
        hooks (HookManager | None): Optional hook manager to attach lifecycle hooks.

    Raises:
        FlowSignal: Always raises the provided signal when the action is run.
    """

    def __init__(self, name: str, signal: FlowSignal, hooks: HookManager | None = None):
        self.signal = signal
        super().__init__(name, action=self.raise_signal, hooks=hooks)

    async def raise_signal(self, *args, **kwargs):
        """
        Raises the configured `FlowSignal`.

        This method is called internally by the Falyx runtime and is the core
        behavior of the action. All hooks surrounding execution are still triggered.
        """
        raise self.signal

    @property
    def signal(self):
        """Returns the configured `FlowSignal` instance."""
        return self._signal

    @signal.setter
    def signal(self, value: FlowSignal):
        """
        Validates that the provided value is a `FlowSignal`.

        Raises:
            TypeError: If `value` is not an instance of `FlowSignal`.
        """
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
