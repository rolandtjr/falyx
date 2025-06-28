# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""action_mixins.py"""
from typing import Sequence

from falyx.action.base_action import BaseAction


class ActionListMixin:
    """Mixin for managing a list of actions."""

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
        """Removes an action by name."""
        self.actions = [action for action in self.actions if action.name != name]

    def has_action(self, name: str) -> bool:
        """Checks if an action with the given name exists."""
        return any(action.name == name for action in self.actions)

    def get_action(self, name: str) -> BaseAction | None:
        """Retrieves an action by name."""
        for action in self.actions:
            if action.name == name:
                return action
        return None
