# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines `MenuAction`, a one-shot, interactive menu-style Falyx Action that presents
a set of labeled options to the user and executes the corresponding action based on
their selection.

Unlike the persistent top-level Falyx menu, `MenuAction` is intended for embedded,
self-contained decision points within a workflow. It supports both interactive and
non-interactive (headless) usage, integrates fully with the Falyx hook lifecycle,
and allows optional defaulting or input injection from previous actions.

Each selectable item is defined in a `MenuOptionMap`, mapping a single-character or
keyword to a `MenuOption`, which includes a description and a corresponding `BaseAction`.

Key Features:
- Renders a Rich-powered multi-column menu table
- Accepts custom prompt sessions or tables
- Supports `last_result` injection for context-aware defaults
- Gracefully handles `BackSignal` and `QuitSignal` for flow control
- Compatible with preview trees and introspection tools

Use Cases:
- In-workflow submenus or branches
- Interactive control points in chained or grouped workflows
- Configurable menus for multi-step user-driven automation

Example:
    MenuAction(
        name="SelectEnv",
        menu_options=MenuOptionMap(options={
            "D": MenuOption("Deploy to Dev", DeployDevAction()),
            "P": MenuOption("Deploy to Prod", DeployProdAction()),
        }),
        default_selection="D",
    )

This module is ideal for enabling structured, discoverable, and declarative
menus in both interactive and programmatic CLI automation.
"""
from typing import Any

from prompt_toolkit import PromptSession
from rich.table import Table
from rich.tree import Tree

from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.logger import logger
from falyx.menu import MenuOptionMap
from falyx.prompt_utils import rich_text_to_prompt_text
from falyx.selection import prompt_for_selection, render_table_base
from falyx.signals import BackSignal, CancelSignal, QuitSignal
from falyx.themes import OneColors
from falyx.utils import chunks


class MenuAction(BaseAction):
    """
    MenuAction displays a one-time interactive menu of predefined options,
    each mapped to a corresponding Action.

    Unlike the main Falyx menu system, `MenuAction` is intended for scoped,
    self-contained selection logic—ideal for small in-flow menus, decision branches,
    or embedded control points in larger workflows.

    Each selectable item is defined in a `MenuOptionMap`, which maps a string key
    to a `MenuOption`, bundling a description and a callable Action.

    Key Features:
    - One-shot selection from labeled actions
    - Optional default or last_result-based selection
    - Full hook lifecycle (before, success, error, after, teardown)
    - Works with or without rendering a table (for headless use)
    - Compatible with `BackSignal` and `QuitSignal` for graceful control flow exits

    Args:
        name (str): Name of the action. Used for logging and debugging.
        menu_options (MenuOptionMap): Mapping of keys to `MenuOption` objects.
        title (str): Table title displayed when prompting the user.
        columns (int): Number of columns in the rendered table.
        prompt_message (str): Prompt text displayed before selection.
        default_selection (str): Key to use if no user input is provided.
        inject_last_result (bool): Whether to inject `last_result` into args/kwargs.
        inject_into (str): Key under which to inject `last_result`.
        prompt_session (PromptSession | None): Custom session for Prompt Toolkit input.
        never_prompt (bool): If True, skips interaction and uses default or last_result.
        include_reserved (bool): Whether to include reserved keys (like 'X' for Exit).
        show_table (bool): Whether to render the Rich menu table.
        custom_table (Table | None): Pre-rendered Rich Table (bypasses auto-building).

    Returns:
        Any: The result of the selected option's Action.

    Raises:
        BackSignal: When the user chooses to return to a previous menu.
        QuitSignal: When the user chooses to exit the program.
        ValueError: If `never_prompt=True` but no default selection is resolvable.
        Exception: Any error raised during the execution of the selected Action.

    Example:
        MenuAction(
            name="ChooseBranch",
            menu_options=MenuOptionMap(options={
                "A": MenuOption("Run analysis", ActionGroup(...)),
                "B": MenuOption("Run report", Action(...)),
            }),
        )
    """

    def __init__(
        self,
        name: str,
        menu_options: MenuOptionMap,
        *,
        title: str = "Select an option",
        columns: int = 2,
        prompt_message: str = "Select > ",
        default_selection: str = "",
        inject_last_result: bool = False,
        inject_into: str = "last_result",
        prompt_session: PromptSession | None = None,
        never_prompt: bool = False,
        include_reserved: bool = True,
        show_table: bool = True,
        custom_table: Table | None = None,
    ):
        super().__init__(
            name,
            inject_last_result=inject_last_result,
            inject_into=inject_into,
            never_prompt=never_prompt,
        )
        self.menu_options = menu_options
        self.title = title
        self.columns = columns
        self.prompt_message = rich_text_to_prompt_text(prompt_message)
        self.default_selection = default_selection
        self.prompt_session = prompt_session or PromptSession(
            interrupt_exception=CancelSignal
        )
        self.include_reserved = include_reserved
        self.show_table = show_table
        self.custom_table = custom_table

    def _build_table(self) -> Table:
        if self.custom_table:
            return self.custom_table
        table = render_table_base(
            title=self.title,
            columns=self.columns,
        )
        for chunk in chunks(
            self.menu_options.items(include_reserved=self.include_reserved), self.columns
        ):
            row = []
            for key, option in chunk:
                row.append(option.render(key))
            table.add_row(*row)
        return table

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
                table = self._build_table()
                key_ = await prompt_for_selection(
                    self.menu_options.keys(),
                    table,
                    default_selection=self.default_selection,
                    prompt_session=self.prompt_session,
                    prompt_message=self.prompt_message,
                    show_table=self.show_table,
                )
                if isinstance(key_, str):
                    key = key_
                else:
                    assert False, "Unreachable, MenuAction only supports single selection"
            option = self.menu_options[key]
            result = await option.action(*args, **kwargs)
            context.result = result
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return result

        except BackSignal:
            logger.debug("[%s][BackSignal] <- Returning to previous menu", self.name)
            return None
        except QuitSignal:
            logger.debug("[%s][QuitSignal] <- Exiting application", self.name)
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
        label = f"[{OneColors.DARK_YELLOW_b}]📋 MenuAction[/] '{self.name}'"
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
            f"MenuAction(name={self.name!r}, options={list(self.menu_options.keys())!r}, "
            f"default_selection={self.default_selection!r}, "
            f"include_reserved={self.include_reserved}, "
            f"prompt={'off' if self.never_prompt else 'on'})"
        )
