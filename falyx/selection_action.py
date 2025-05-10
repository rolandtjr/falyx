# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""selection_action.py"""
from typing import Any

from prompt_toolkit import PromptSession
from rich.console import Console
from rich.tree import Tree

from falyx.action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.selection import (
    SelectionOption,
    prompt_for_index,
    prompt_for_selection,
    render_selection_dict_table,
    render_selection_indexed_table,
)
from falyx.themes.colors import OneColors
from falyx.utils import CaseInsensitiveDict, logger


class SelectionAction(BaseAction):
    def __init__(
        self,
        name: str,
        selections: list[str] | set[str] | tuple[str, ...] | dict[str, SelectionOption],
        *,
        title: str = "Select an option",
        columns: int = 2,
        prompt_message: str = "Select > ",
        default_selection: str = "",
        inject_last_result: bool = False,
        inject_into: str = "last_result",
        return_key: bool = False,
        console: Console | None = None,
        prompt_session: PromptSession | None = None,
        never_prompt: bool = False,
        show_table: bool = True,
    ):
        super().__init__(
            name,
            inject_last_result=inject_last_result,
            inject_into=inject_into,
            never_prompt=never_prompt,
        )
        self.selections: list[str] | CaseInsensitiveDict = selections
        self.return_key = return_key
        self.title = title
        self.columns = columns
        self.console = console or Console(color_system="auto")
        self.prompt_session = prompt_session or PromptSession()
        self.default_selection = default_selection
        self.prompt_message = prompt_message
        self.show_table = show_table

    @property
    def selections(self) -> list[str] | CaseInsensitiveDict:
        return self._selections

    @selections.setter
    def selections(
        self, value: list[str] | set[str] | tuple[str, ...] | dict[str, SelectionOption]
    ):
        if isinstance(value, (list, tuple, set)):
            self._selections: list[str] | CaseInsensitiveDict = list(value)
        elif isinstance(value, dict):
            cid = CaseInsensitiveDict()
            cid.update(value)
            self._selections = cid
        else:
            raise TypeError(
                f"'selections' must be a list[str] or dict[str, SelectionOption], got {type(value).__name__}"
            )

    async def _run(self, *args, **kwargs) -> Any:
        kwargs = self._maybe_inject_last_result(kwargs)
        context = ExecutionContext(
            name=self.name,
            args=args,
            kwargs=kwargs,
            action=self,
        )

        effective_default = str(self.default_selection)
        maybe_result = str(self.last_result)
        if isinstance(self.selections, dict):
            if maybe_result in self.selections:
                effective_default = maybe_result
            elif self.inject_last_result:
                logger.warning(
                    "[%s] Injected last result '%s' not found in selections",
                    self.name,
                    maybe_result,
                )
        elif isinstance(self.selections, list):
            if maybe_result.isdigit() and int(maybe_result) in range(
                len(self.selections)
            ):
                effective_default = maybe_result
            elif self.inject_last_result:
                logger.warning(
                    "[%s] Injected last result '%s' not found in selections",
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
            if isinstance(self.selections, list):
                table = render_selection_indexed_table(
                    title=self.title,
                    selections=self.selections,
                    columns=self.columns,
                )
                if not self.never_prompt:
                    index = await prompt_for_index(
                        len(self.selections) - 1,
                        table,
                        default_selection=effective_default,
                        console=self.console,
                        prompt_session=self.prompt_session,
                        prompt_message=self.prompt_message,
                        show_table=self.show_table,
                    )
                else:
                    index = effective_default
                result = self.selections[int(index)]
            elif isinstance(self.selections, dict):
                table = render_selection_dict_table(
                    title=self.title, selections=self.selections, columns=self.columns
                )
                if not self.never_prompt:
                    key = await prompt_for_selection(
                        self.selections.keys(),
                        table,
                        default_selection=effective_default,
                        console=self.console,
                        prompt_session=self.prompt_session,
                        prompt_message=self.prompt_message,
                        show_table=self.show_table,
                    )
                else:
                    key = effective_default
                result = key if self.return_key else self.selections[key].value
            else:
                raise TypeError(
                    f"'selections' must be a list[str] or dict[str, tuple[str, Any]], got {type(self.selections).__name__}"
                )
            context.result = result
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return result
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
        label = f"[{OneColors.LIGHT_RED}]🧭 SelectionAction[/] '{self.name}'"
        tree = parent.add(label) if parent else Tree(label)

        if isinstance(self.selections, list):
            sub = tree.add(f"[dim]Type:[/] List[str] ({len(self.selections)} items)")
            for i, item in enumerate(self.selections[:10]):  # limit to 10
                sub.add(f"[dim]{i}[/]: {item}")
            if len(self.selections) > 10:
                sub.add(f"[dim]... ({len(self.selections) - 10} more)[/]")
        elif isinstance(self.selections, dict):
            sub = tree.add(
                f"[dim]Type:[/] Dict[str, (str, Any)] ({len(self.selections)} items)"
            )
            for i, (key, option) in enumerate(list(self.selections.items())[:10]):
                sub.add(f"[dim]{key}[/]: {option.description}")
            if len(self.selections) > 10:
                sub.add(f"[dim]... ({len(self.selections) - 10} more)[/]")
        else:
            tree.add("[bold red]Invalid selections type[/]")
            return

        tree.add(f"[dim]Default:[/] '{self.default_selection or self.last_result}'")
        tree.add(f"[dim]Return:[/] {'Key' if self.return_key else 'Value'}")
        tree.add(f"[dim]Prompt:[/] {'Disabled' if self.never_prompt else 'Enabled'}")

        if not parent:
            self.console.print(tree)

    def __str__(self) -> str:
        selection_type = (
            "List"
            if isinstance(self.selections, list)
            else "Dict" if isinstance(self.selections, dict) else "Unknown"
        )
        return (
            f"SelectionAction(name={self.name!r}, type={selection_type}, "
            f"default_selection={self.default_selection!r}, "
            f"return_key={self.return_key}, prompt={'off' if self.never_prompt else 'on'})"
        )
