# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Provides reusable mixins for managing collections of `BaseAction` instances
within composite Falyx actions such as `ActionGroup` or `ChainedAction`.

The primary export, `ActionListMixin`, encapsulates common functionality for
maintaining a mutable list of named actions—such as adding, removing, or retrieving
actions by name—without duplicating logic across composite action types.
"""

from typing import Sequence

from falyx.action.base_action import BaseAction


class ActionListMixin:
    """
    Mixin for managing a list of named `BaseAction` objects.

    Provides helper methods for setting, adding, removing, checking, and
    retrieving actions in composite Falyx constructs like `ActionGroup`.

    Attributes:
        actions (list[BaseAction]): The internal list of managed actions.

    Methods:
        set_actions(actions): Replaces all current actions with the given list.
        add_action(action): Adds a new action to the list.
        remove_action(name): Removes an action by its name.
        has_action(name): Returns True if an action with the given name exists.
        get_action(name): Returns the action matching the name, or None.
    """

    def __init__(self) -> None:
        self.actions: list[BaseAction] = []

    def set_actions(self, actions: Sequence[BaseAction]) -> None:
        """Replaces the current action list with a new one."""
        self.actions.clear()
        for action in actions:
            self.add_action(action)

    def add_action(self, action: BaseAction) -> None:
        """Adds an action to the list."""
        self.actions.append(action)

    def remove_action(self, name: str) -> None:
        """Removes all actions with the given name."""
        self.actions = [action for action in self.actions if action.name != name]

    def has_action(self, name: str) -> bool:
        """Checks if an action with the given name exists."""
        return any(action.name == name for action in self.actions)

    def get_action(self, name: str) -> BaseAction | None:
        """Retrieves a single action with the given name."""
        for action in self.actions:
            if action.name == name:
                return action
        return None
