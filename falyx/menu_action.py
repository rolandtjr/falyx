# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""menu_action.py"""
from dataclasses import dataclass
from typing import Any

from prompt_toolkit import PromptSession
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from falyx.action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.selection import prompt_for_selection, render_table_base
from falyx.signal_action import SignalAction
from falyx.signals import BackSignal, QuitSignal
from falyx.themes.colors import OneColors
from falyx.utils import CaseInsensitiveDict, chunks, logger


@dataclass
class MenuOption:
    description: str
    action: BaseAction
    style: str = OneColors.WHITE

    def __post_init__(self):
        if not isinstance(self.description, str):
            raise TypeError("MenuOption description must be a string.")
        if not isinstance(self.action, BaseAction):
            raise TypeError("MenuOption action must be a BaseAction instance.")

    def render(self, key: str) -> str:
        """Render the menu option for display."""
        return f"[{OneColors.WHITE}][{key}][/] [{self.style}]{self.description}[/]"


class MenuOptionMap(CaseInsensitiveDict):
    """
    Manages menu options including validation, reserved key protection,
    and special signal entries like Quit and Back.
    """

    RESERVED_KEYS = {"Q", "B"}

    def __init__(
        self,
        options: dict[str, MenuOption] | None = None,
        allow_reserved: bool = False,
    ):
        super().__init__()
        self.allow_reserved = allow_reserved
        if options:
            self.update(options)
        self._inject_reserved_defaults()

    def _inject_reserved_defaults(self):
        self._add_reserved(
            "Q",
            MenuOption("Exit", SignalAction("Quit", QuitSignal()), OneColors.DARK_RED),
        )
        self._add_reserved(
            "B",
            MenuOption("Back", SignalAction("Back", BackSignal()), OneColors.DARK_YELLOW),
        )

    def _add_reserved(self, key: str, option: MenuOption) -> None:
        """Add a reserved key, bypassing validation."""
        norm_key = key.upper()
        super().__setitem__(norm_key, option)

    def __setitem__(self, key: str, option: MenuOption) -> None:
        if not isinstance(option, MenuOption):
            raise TypeError(f"Value for key '{key}' must be a MenuOption.")
        norm_key = key.upper()
        if norm_key in self.RESERVED_KEYS and not self.allow_reserved:
            raise ValueError(
                f"Key '{key}' is reserved and cannot be used in MenuOptionMap."
            )
        super().__setitem__(norm_key, option)

    def __delitem__(self, key: str) -> None:
        if key.upper() in self.RESERVED_KEYS and not self.allow_reserved:
            raise ValueError(f"Cannot delete reserved option '{key}'.")
        super().__delitem__(key)

    def items(self, include_reserved: bool = True):
        for k, v in super().items():
            if not include_reserved and k in self.RESERVED_KEYS:
                continue
            yield k, v


class MenuAction(BaseAction):
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
        console: Console | None = None,
        prompt_session: PromptSession | None = None,
        never_prompt: bool = False,
        include_reserved: bool = True,
        show_table: bool = True,
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
        self.prompt_message = prompt_message
        self.default_selection = default_selection
        self.console = console or Console(color_system="auto")
        self.prompt_session = prompt_session or PromptSession()
        self.include_reserved = include_reserved
        self.show_table = show_table

    def _build_table(self) -> Table:
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
                f"[{self.name}] 'never_prompt' is True but no valid default_selection was provided."
            )

        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)
            key = effective_default
            if not self.never_prompt:
                table = self._build_table()
                key = await prompt_for_selection(
                    self.menu_options.keys(),
                    table,
                    default_selection=self.default_selection,
                    console=self.console,
                    prompt_session=self.prompt_session,
                    prompt_message=self.prompt_message,
                    show_table=self.show_table,
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
