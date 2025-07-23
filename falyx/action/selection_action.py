# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines `SelectionAction`, a highly flexible Falyx Action for interactive or headless
selection from a list or dictionary of user-defined options.

This module powers workflows that require prompting the user for input, selecting
configuration presets, branching execution paths, or collecting multiple values
in a type-safe, hook-compatible, and composable way.

Key Features:
- Supports both flat lists and structured dictionaries (`SelectionOptionMap`)
- Handles single or multi-selection with configurable separators
- Returns results in various formats (key, value, description, item, or mapping)
- Integrates fully with Falyx lifecycle hooks and `last_result` injection
- Works in interactive (`prompt_toolkit`) and non-interactive (headless) modes
- Renders a Rich-based table preview for diagnostics or dry runs

Usage Scenarios:
- Guided CLI wizards or configuration menus
- Dynamic branching or conditional step logic
- User-driven parameterization in chained workflows
- Reusable pickers for environments, files, datasets, etc.

Example:
    SelectionAction(
        name="ChooseMode",
        selections={"dev": "Development", "prod": "Production"},
        return_type="key"
    )

This module is foundational to creating expressive, user-centered CLI experiences
within Falyx while preserving reproducibility and automation friendliness.
"""
from typing import Any

from prompt_toolkit import PromptSession
from rich.tree import Tree

from falyx.action.action_types import SelectionReturnType
from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.logger import logger
from falyx.prompt_utils import rich_text_to_prompt_text
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
    A Falyx Action for interactively or programmatically selecting one or more items
    from a list or dictionary of options.

    `SelectionAction` supports both `list[str]` and `dict[str, SelectionOption]`
    inputs. It renders a prompt (unless `never_prompt=True`), validates user input
    or injected defaults, and returns a structured result based on the specified
    `return_type`.

    It is commonly used for item pickers, confirmation flows, dynamic parameterization,
    or guided workflows in interactive or headless CLI pipelines.

    Features:
    - Supports single or multiple selections (`number_selections`)
    - Dictionary mode allows rich metadata (description, value, style)
    - Flexible return values: key(s), value(s), item(s), description(s), or mappings
    - Fully hookable lifecycle (`before`, `on_success`, `on_error`, `after`, `on_teardown`)
    - Default selection logic supports previous results (`last_result`)
    - Can run in headless mode using `never_prompt` and fallback defaults

    Args:
        name (str): Action name for tracking and logging.
        selections (list[str] | dict[str, SelectionOption] | dict[str, Any]):
            The available choices. If a plain dict is passed, values are converted
            into `SelectionOption` instances.
        title (str): Title shown in the selection UI (default: "Select an option").
        columns (int): Number of columns in the selection table.
        prompt_message (str): Input prompt for the user (default: "Select > ").
        default_selection (str | list[str]): Key(s) or index(es) used as fallback selection.
        number_selections (int | str): Max number of choices allowed (or "*" for unlimited).
        separator (str): Character used to separate multi-selections (default: ",").
        allow_duplicates (bool): Whether duplicate selections are allowed.
        inject_last_result (bool): If True, attempts to inject the last result as default.
        inject_into (str): The keyword name for injected value (default: "last_result").
        return_type (SelectionReturnType | str): The type of result to return.
        prompt_session (PromptSession | None): Reused or customized prompt_toolkit session.
        never_prompt (bool): If True, skips prompting and uses default_selection or last_result.
        show_table (bool): Whether to render the selection table before prompting.

    Returns:
        Any: The selected result(s), shaped according to `return_type`.

    Raises:
        CancelSignal: If the user chooses the cancel option.
        ValueError: If configuration is invalid or no selection can be resolved.
        TypeError: If `selections` is not a supported type.

    Example:
        SelectionAction(
            name="PickEnv",
            selections={"dev": "Development", "prod": "Production"},
            return_type="key",
        )

    This Action supports use in both interactive menus and chained, non-interactive CLI flows.
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
        default_selection: str | list[str] = "",
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
        self.return_type: SelectionReturnType = SelectionReturnType(return_type)
        self.title = title
        self.columns = columns
        self.prompt_session = prompt_session or PromptSession(
            interrupt_exception=CancelSignal
        )
        self.default_selection = default_selection
        self.number_selections = number_selections
        self.separator = separator
        self.allow_duplicates = allow_duplicates
        self.prompt_message = rich_text_to_prompt_text(prompt_message)
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

    async def _resolve_effective_default(self) -> str:
        effective_default: str | list[str] = self.default_selection
        maybe_result = self.last_result
        if self.number_selections == 1:
            if isinstance(effective_default, list):
                effective_default = effective_default[0] if effective_default else ""
            elif isinstance(maybe_result, list):
                maybe_result = maybe_result[0] if maybe_result else ""
            default = await self._resolve_single_default(maybe_result)
            if not default:
                default = await self._resolve_single_default(effective_default)
            if not default and self.inject_last_result:
                logger.warning(
                    "[%s] Injected last result '%s' not found in selections",
                    self.name,
                    maybe_result,
                )
            return default

        if maybe_result and isinstance(maybe_result, list):
            maybe_result = [
                await self._resolve_single_default(item) for item in maybe_result
            ]
            if (
                maybe_result
                and self.number_selections != "*"
                and len(maybe_result) != self.number_selections
            ):
                raise ValueError(
                    f"[{self.name}] 'number_selections' is {self.number_selections}, "
                    f"but last_result has a different length: {len(maybe_result)}."
                )
            return self.separator.join(maybe_result)
        elif effective_default and isinstance(effective_default, list):
            effective_default = [
                await self._resolve_single_default(item) for item in effective_default
            ]
            if (
                effective_default
                and self.number_selections != "*"
                and len(effective_default) != self.number_selections
            ):
                raise ValueError(
                    f"[{self.name}] 'number_selections' is {self.number_selections}, "
                    f"but default_selection has a different length: {len(effective_default)}."
                )
            return self.separator.join(effective_default)
        if self.inject_last_result:
            logger.warning(
                "[%s] Injected last result '%s' not found in selections",
                self.name,
                maybe_result,
            )
        return ""

    async def _resolve_single_default(self, maybe_result: str) -> str:
        effective_default = ""
        if isinstance(self.selections, dict):
            if str(maybe_result) in self.selections:
                effective_default = str(maybe_result)
            elif maybe_result in (
                selection.value for selection in self.selections.values()
            ):
                selection = [
                    key
                    for key, sel in self.selections.items()
                    if sel.value == maybe_result
                ]
                if selection:
                    effective_default = selection[0]
            elif maybe_result in (
                selection.description for selection in self.selections.values()
            ):
                selection = [
                    key
                    for key, sel in self.selections.items()
                    if sel.description == maybe_result
                ]
                if selection:
                    effective_default = selection[0]
        elif isinstance(self.selections, list):
            if str(maybe_result).isdigit() and int(maybe_result) in range(
                len(self.selections)
            ):
                effective_default = maybe_result
            elif maybe_result in self.selections:
                effective_default = str(self.selections.index(maybe_result))
        return effective_default

    async def _run(self, *args, **kwargs) -> Any:
        kwargs = self._maybe_inject_last_result(kwargs)
        context = ExecutionContext(
            name=self.name,
            args=args,
            kwargs=kwargs,
            action=self,
        )

        effective_default = await self._resolve_effective_default()

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
                if effective_default is None or isinstance(effective_default, int):
                    effective_default = ""

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
                    if effective_default and self.number_selections == 1:
                        indices = int(effective_default)
                    elif effective_default:
                        indices = [
                            int(index)
                            for index in effective_default.split(self.separator)
                        ]
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
                    if effective_default and self.number_selections == 1:
                        keys = effective_default
                    elif effective_default:
                        keys = effective_default.split(self.separator)
                    else:
                        raise ValueError(
                            f"[{self.name}] 'never_prompt' is True but no valid "
                            "default_selection was provided."
                        )
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
            for i, item in enumerate(self.selections[:10]):
                sub.add(f"[dim]{i}[/]: {item}")
            if len(self.selections) > 10:
                sub.add(f"[dim]... ({len(self.selections) - 10} more)[/]")
        elif isinstance(self.selections, dict):
            sub = tree.add(
                f"[dim]Type:[/] Dict[str, SelectionOption] ({len(self.selections)} items)"
            )
            for i, (key, option) in enumerate(list(self.selections.items())[:10]):
                sub.add(f"[dim]{key}[/]: {option.description}")
            if len(self.selections) > 10:
                sub.add(f"[dim]... ({len(self.selections) - 10} more)[/]")
        else:
            tree.add(f"[{OneColors.DARK_RED_b}]Invalid selections type[/]")
            return

        default = self.default_selection or self.last_result
        if isinstance(default, list):
            default_display = self.separator.join(str(d) for d in default)
        else:
            default_display = str(default or "")

        tree.add(f"[dim]Default:[/] '{default_display}'")

        return_behavior = {
            "KEY": "selected key(s)",
            "VALUE": "mapped value(s)",
            "DESCRIPTION": "description(s)",
            "ITEMS": "SelectionOption object(s)",
            "DESCRIPTION_VALUE": "{description: value}",
        }.get(self.return_type.name, self.return_type.name)

        tree.add(
            f"[dim]Return:[/] {self.return_type.name.capitalize()} → {return_behavior}"
        )
        tree.add(f"[dim]Prompt:[/] {'Disabled' if self.never_prompt else 'Enabled'}")
        tree.add(f"[dim]Columns:[/] {self.columns}")
        tree.add(
            f"[dim]Multi-select:[/] {'Yes' if self.number_selections != 1 else 'No'}"
        )

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
