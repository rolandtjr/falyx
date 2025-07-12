# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""selection_action.py"""
from typing import Any

from prompt_toolkit import PromptSession
from rich.tree import Tree

from falyx.action.action_types import SelectionReturnType
from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.logger import logger
from falyx.selection import (
    SelectionOption,
    SelectionOptionMap,
    prompt_for_index,
    prompt_for_selection,
    render_selection_dict_table,
    render_selection_indexed_table,
)
from falyx.signals import CancelSignal
from falyx.themes import OneColors


class SelectionAction(BaseAction):
    """
    A selection action that prompts the user to select an option from a list or
    dictionary. The selected option is then returned as the result of the action.

    If return_key is True, the key of the selected option is returned instead of
    the value.
    """

    def __init__(
        self,
        name: str,
        selections: (
            list[str]
            | set[str]
            | tuple[str, ...]
            | dict[str, SelectionOption]
            | dict[str, Any]
        ),
        *,
        title: str = "Select an option",
        columns: int = 5,
        prompt_message: str = "Select > ",
        default_selection: str = "",
        number_selections: int | str = 1,
        separator: str = ",",
        allow_duplicates: bool = False,
        inject_last_result: bool = False,
        inject_into: str = "last_result",
        return_type: SelectionReturnType | str = "value",
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
        # Setter normalizes to correct type, mypy can't infer that
        self.selections: list[str] | SelectionOptionMap = selections  # type: ignore[assignment]
        self.return_type: SelectionReturnType = self._coerce_return_type(return_type)
        self.title = title
        self.columns = columns
        self.prompt_session = prompt_session or PromptSession()
        self.default_selection = default_selection
        self.number_selections = number_selections
        self.separator = separator
        self.allow_duplicates = allow_duplicates
        self.prompt_message = prompt_message
        self.show_table = show_table

    @property
    def number_selections(self) -> int | str:
        return self._number_selections

    @number_selections.setter
    def number_selections(self, value: int | str):
        if isinstance(value, int) and value > 0:
            self._number_selections: int | str = value
        elif isinstance(value, str):
            if value not in ("*"):
                raise ValueError("number_selections string must be '*'")
            self._number_selections = value
        else:
            raise ValueError("number_selections must be a positive integer or '*'")

    def _coerce_return_type(
        self, return_type: SelectionReturnType | str
    ) -> SelectionReturnType:
        if isinstance(return_type, SelectionReturnType):
            return return_type
        return SelectionReturnType(return_type)

    @property
    def selections(self) -> list[str] | SelectionOptionMap:
        return self._selections

    @selections.setter
    def selections(
        self, value: list[str] | set[str] | tuple[str, ...] | dict[str, SelectionOption]
    ):
        if isinstance(value, (list, tuple, set)):
            self._selections: list[str] | SelectionOptionMap = list(value)
        elif isinstance(value, dict):
            som = SelectionOptionMap()
            if all(isinstance(key, str) for key in value) and all(
                not isinstance(value[key], SelectionOption) for key in value
            ):
                som.update(
                    {
                        str(index): SelectionOption(key, option)
                        for index, (key, option) in enumerate(value.items())
                    }
                )
            elif all(isinstance(key, str) for key in value) and all(
                isinstance(value[key], SelectionOption) for key in value
            ):
                som.update(value)
            else:
                raise ValueError("Invalid dictionary format. Keys must be strings")
            self._selections = som
        else:
            raise TypeError(
                "'selections' must be a list[str] or dict[str, SelectionOption], "
                f"got {type(value).__name__}"
            )

    def _find_cancel_key(self) -> str:
        """Find the cancel key in the selections."""
        if isinstance(self.selections, dict):
            for index in range(len(self.selections) + 1):
                if str(index) not in self.selections:
                    return str(index)
        return str(len(self.selections))

    @property
    def cancel_key(self) -> str:
        return self._cancel_key

    @cancel_key.setter
    def cancel_key(self, value: str) -> None:
        """Set the cancel key for the selection."""
        if not isinstance(value, str):
            raise TypeError("Cancel key must be a string.")
        if isinstance(self.selections, dict) and value in self.selections:
            raise ValueError(
                "Cancel key cannot be one of the selection keys. "
                f"Current selections: {self.selections}"
            )
        if isinstance(self.selections, list):
            if not value.isdigit() or int(value) > len(self.selections):
                raise ValueError(
                    "cancel_key must be a digit and not greater than the number of selections."
                )
        self._cancel_key = value

    def cancel_formatter(self, index: int, selection: str) -> str:
        """Format the cancel option for display."""
        if self.cancel_key == str(index):
            return f"[{index}] [{OneColors.DARK_RED}]Cancel[/]"
        return f"[{index}] {selection}"

    def get_infer_target(self) -> tuple[None, None]:
        return None, None

    def _get_result_from_keys(self, keys: str | list[str]) -> Any:
        if not isinstance(self.selections, dict):
            raise TypeError("Selections must be a dictionary to get result by keys.")
        if self.return_type == SelectionReturnType.KEY:
            result: Any = keys
        elif self.return_type == SelectionReturnType.VALUE:
            if isinstance(keys, list):
                result = [self.selections[key].value for key in keys]
            elif isinstance(keys, str):
                result = self.selections[keys].value
        elif self.return_type == SelectionReturnType.ITEMS:
            if isinstance(keys, list):
                result = {key: self.selections[key] for key in keys}
            elif isinstance(keys, str):
                result = {keys: self.selections[keys]}
        elif self.return_type == SelectionReturnType.DESCRIPTION:
            if isinstance(keys, list):
                result = [self.selections[key].description for key in keys]
            elif isinstance(keys, str):
                result = self.selections[keys].description
        elif self.return_type == SelectionReturnType.DESCRIPTION_VALUE:
            if isinstance(keys, list):
                result = {
                    self.selections[key].description: self.selections[key].value
                    for key in keys
                }
            elif isinstance(keys, str):
                result = {self.selections[keys].description: self.selections[keys].value}
        else:
            raise ValueError(f"Unsupported return type: {self.return_type}")
        return result

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
                f"[{self.name}] 'never_prompt' is True but no valid default_selection "
                "or usable last_result was available."
            )

        context.start_timer()
        try:
            self.cancel_key = self._find_cancel_key()
            await self.hooks.trigger(HookType.BEFORE, context)
            if isinstance(self.selections, list):
                table = render_selection_indexed_table(
                    title=self.title,
                    selections=self.selections + ["Cancel"],
                    columns=self.columns,
                    formatter=self.cancel_formatter,
                )
                if not self.never_prompt:
                    indices: int | list[int] = await prompt_for_index(
                        len(self.selections),
                        table,
                        default_selection=effective_default,
                        prompt_session=self.prompt_session,
                        prompt_message=self.prompt_message,
                        show_table=self.show_table,
                        number_selections=self.number_selections,
                        separator=self.separator,
                        allow_duplicates=self.allow_duplicates,
                        cancel_key=self.cancel_key,
                    )
                else:
                    if effective_default:
                        indices = int(effective_default)
                    else:
                        raise ValueError(
                            f"[{self.name}] 'never_prompt' is True but no valid "
                            "default_selection was provided."
                        )

                if indices == int(self.cancel_key):
                    raise CancelSignal("User cancelled the selection.")
                if isinstance(indices, list):
                    result: str | list[str] = [
                        self.selections[index] for index in indices
                    ]
                elif isinstance(indices, int):
                    result = self.selections[indices]
                else:
                    assert False, "unreachable"
            elif isinstance(self.selections, dict):
                cancel_option = {
                    self.cancel_key: SelectionOption(
                        description="Cancel", value=CancelSignal, style=OneColors.DARK_RED
                    )
                }
                table = render_selection_dict_table(
                    title=self.title,
                    selections=self.selections | cancel_option,
                    columns=self.columns,
                )
                if not self.never_prompt:
                    keys = await prompt_for_selection(
                        (self.selections | cancel_option).keys(),
                        table,
                        default_selection=effective_default,
                        prompt_session=self.prompt_session,
                        prompt_message=self.prompt_message,
                        show_table=self.show_table,
                        number_selections=self.number_selections,
                        separator=self.separator,
                        allow_duplicates=self.allow_duplicates,
                        cancel_key=self.cancel_key,
                    )
                else:
                    keys = effective_default
                if keys == self.cancel_key:
                    raise CancelSignal("User cancelled the selection.")

                result = self._get_result_from_keys(keys)
            else:
                raise TypeError(
                    "'selections' must be a list[str] or dict[str, Any], "
                    f"got {type(self.selections).__name__}"
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
            tree.add(f"[{OneColors.DARK_RED_b}]Invalid selections type[/]")
            return

        tree.add(f"[dim]Default:[/] '{self.default_selection or self.last_result}'")
        tree.add(f"[dim]Return:[/] {self.return_type.name.capitalize()}")
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
            f"return_type={self.return_type!r}, "
            f"prompt={'off' if self.never_prompt else 'on'})"
        )
