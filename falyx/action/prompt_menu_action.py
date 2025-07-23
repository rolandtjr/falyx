# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines `PromptMenuAction`, a Falyx Action that prompts the user to choose from
a list of labeled options using a single-line prompt input. Each option corresponds
to a `MenuOption` that wraps a description and an executable action.

Unlike `MenuAction`, this action renders a flat, inline prompt (e.g., `Option1 | Option2`)
without using a rich table. It is ideal for compact decision points, hotkey-style menus,
or contextual user input flows.

Key Components:
- PromptMenuAction: Inline prompt-driven menu runner
"""
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText, merge_formatted_text
from rich.tree import Tree

from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.logger import logger
from falyx.menu import MenuOptionMap
from falyx.prompt_utils import rich_text_to_prompt_text
from falyx.signals import BackSignal, CancelSignal, QuitSignal
from falyx.themes import OneColors


class PromptMenuAction(BaseAction):
    """
    Displays a single-line interactive prompt for selecting an option from a menu.

    `PromptMenuAction` is a lightweight alternative to `MenuAction`, offering a more
    compact selection interface. Instead of rendering a full table, it displays
    available keys inline as a placeholder (e.g., `A | B | C`) and accepts the user's
    input to execute the associated action.

    Each key is defined in a `MenuOptionMap`, which maps to a `MenuOption` containing
    a description and an executable action.

    Key Features:
    - Minimal UI: rendered as a single prompt line with placeholder
    - Optional fallback to `default_selection` or injected `last_result`
    - Fully hookable lifecycle (before, success, error, after, teardown)
    - Supports reserved keys and structured error recovery

    Args:
        name (str): Name of the action. Used for logging and debugging.
        menu_options (MenuOptionMap): A mapping of keys to `MenuOption` objects.
        prompt_message (str): Text displayed before user input (default: "Select > ").
        default_selection (str): Fallback key if no input is provided.
        inject_last_result (bool): Whether to use `last_result` as a fallback input key.
        inject_into (str): Kwarg name under which to inject the last result.
        prompt_session (PromptSession | None): Custom Prompt Toolkit session.
        never_prompt (bool): If True, skips user input and uses `default_selection`.
        include_reserved (bool): Whether to include reserved keys in logic and preview.

    Returns:
        Any: The result of the selected option's action.

    Raises:
        BackSignal: If the user signals to return to the previous menu.
        QuitSignal: If the user signals to exit the CLI entirely.
        ValueError: If `never_prompt` is enabled but no fallback is available.
        Exception: If an error occurs during the action's execution.

    Example:
        PromptMenuAction(
            name="HotkeyPrompt",
            menu_options=MenuOptionMap(options={
                "R": MenuOption("Run", ChainedAction(...)),
                "S": MenuOption("Skip", Action(...)),
            }),
            prompt_message="Choose action > ",
        )
    """

    def __init__(
        self,
        name: str,
        menu_options: MenuOptionMap,
        *,
        prompt_message: str = "Select > ",
        default_selection: str = "",
        inject_last_result: bool = False,
        inject_into: str = "last_result",
        prompt_session: PromptSession | None = None,
        never_prompt: bool = False,
        include_reserved: bool = True,
    ):
        super().__init__(
            name,
            inject_last_result=inject_last_result,
            inject_into=inject_into,
            never_prompt=never_prompt,
        )
        self.menu_options = menu_options
        self.prompt_message = rich_text_to_prompt_text(prompt_message)
        self.default_selection = default_selection
        self.prompt_session = prompt_session or PromptSession(
            interrupt_exception=CancelSignal
        )
        self.include_reserved = include_reserved

    def get_infer_target(self) -> tuple[None, None]:
        return None, None

    async def _run(self, *args, **kwargs) -> Any:
        kwargs = self._maybe_inject_last_result(kwargs)
        context = ExecutionContext(
            name=self.name,
            args=args,
            kwargs=kwargs,
            action=self,
        )

        effective_default = self.default_selection
        maybe_result = str(self.last_result)
        if maybe_result in self.menu_options:
            effective_default = maybe_result
        elif self.inject_last_result:
            logger.warning(
                "[%s] Injected last result '%s' not found in menu options",
                self.name,
                maybe_result,
            )

        if self.never_prompt and not effective_default:
            raise ValueError(
                f"[{self.name}] 'never_prompt' is True but no valid default_selection"
                " was provided."
            )

        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)
            key = effective_default
            if not self.never_prompt:
                placeholder_formatted_text = []
                for index, (key, option) in enumerate(self.menu_options.items()):
                    placeholder_formatted_text.append(option.render_prompt(key))
                    if index < len(self.menu_options) - 1:
                        placeholder_formatted_text.append(
                            FormattedText([(OneColors.WHITE, " | ")])
                        )
                placeholder = merge_formatted_text(placeholder_formatted_text)
                key = await self.prompt_session.prompt_async(
                    message=self.prompt_message, placeholder=placeholder
                )
            option = self.menu_options[key]
            result = await option.action(*args, **kwargs)
            context.result = result
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return result

        except BackSignal:
            logger.debug("[%s][BackSignal] ← Returning to previous menu", self.name)
            return None
        except QuitSignal:
            logger.debug("[%s][QuitSignal] ← Exiting application", self.name)
            raise
        except Exception as error:
            context.exception = error
            await self.hooks.trigger(HookType.ON_ERROR, context)
            raise
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
            er.record(context)

    async def preview(self, parent: Tree | None = None):
        label = f"[{OneColors.LIGHT_YELLOW_b}]📋 PromptMenuAction[/] '{self.name}'"
        tree = parent.add(label) if parent else Tree(label)
        for key, option in self.menu_options.items():
            tree.add(
                f"[dim]{key}[/]: {option.description} → [italic]{option.action.name}[/]"
            )
            await option.action.preview(parent=tree)
        if not parent:
            self.console.print(tree)

    def __str__(self) -> str:
        return (
            f"PromptMenuAction(name={self.name!r}, options={list(self.menu_options.keys())!r}, "
            f"default_selection={self.default_selection!r}, "
            f"include_reserved={self.include_reserved}, "
            f"prompt={'off' if self.never_prompt else 'on'})"
        )
