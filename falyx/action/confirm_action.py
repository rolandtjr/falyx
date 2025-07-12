from __future__ import annotations

from enum import Enum
from typing import Any

from prompt_toolkit import PromptSession
from rich.tree import Tree

from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.logger import logger
from falyx.prompt_utils import confirm_async, should_prompt_user
from falyx.signals import CancelSignal
from falyx.themes import OneColors
from falyx.validators import word_validator, words_validator


class ConfirmType(Enum):
    """Enum for different confirmation types."""

    YES_NO = "yes_no"
    YES_CANCEL = "yes_cancel"
    YES_NO_CANCEL = "yes_no_cancel"
    TYPE_WORD = "type_word"
    OK_CANCEL = "ok_cancel"

    @classmethod
    def choices(cls) -> list[ConfirmType]:
        """Return a list of all hook type choices."""
        return list(cls)

    def __str__(self) -> str:
        """Return the string representation of the confirm type."""
        return self.value


class ConfirmAction(BaseAction):
    """
    Action to confirm an operation with the user.

    There are several ways to confirm an action, such as using a simple
    yes/no prompt. You can also use a confirmation type that requires the user
    to type a specific word or phrase to confirm the action, or use an OK/Cancel
    dialog.

    This action can be used to ensure that the user explicitly agrees to proceed
    with an operation.

    Attributes:
        name (str): Name of the action.
        message (str): The confirmation message to display.
        confirm_type (ConfirmType | str): The type of confirmation to use.
            Options include YES_NO, YES_CANCEL, YES_NO_CANCEL, TYPE_WORD, and OK_CANCEL.
        prompt_session (PromptSession | None): The session to use for input.
        confirm (bool): Whether to prompt the user for confirmation.
        word (str): The word to type for TYPE_WORD confirmation.
        return_last_result (bool): Whether to return the last result of the action.
    """

    def __init__(
        self,
        name: str,
        message: str = "Continue",
        confirm_type: ConfirmType | str = ConfirmType.YES_NO,
        prompt_session: PromptSession | None = None,
        confirm: bool = True,
        word: str = "CONFIRM",
        return_last_result: bool = False,
        inject_last_result: bool = True,
        inject_into: str = "last_result",
    ):
        """
        Initialize the ConfirmAction.

        Args:
            message (str): The confirmation message to display.
            confirm_type (ConfirmType): The type of confirmation to use.
                Options include YES_NO, YES_CANCEL, YES_NO_CANCEL, TYPE_WORD, and OK_CANCEL.
            prompt_session (PromptSession | None): The session to use for input.
            confirm (bool): Whether to prompt the user for confirmation.
            word (str): The word to type for TYPE_WORD confirmation.
            return_last_result (bool): Whether to return the last result of the action.
        """
        super().__init__(
            name=name,
            inject_last_result=inject_last_result,
            inject_into=inject_into,
        )
        self.message = message
        self.confirm_type = self._coerce_confirm_type(confirm_type)
        self.prompt_session = prompt_session or PromptSession()
        self.confirm = confirm
        self.word = word
        self.return_last_result = return_last_result

    def _coerce_confirm_type(self, confirm_type: ConfirmType | str) -> ConfirmType:
        """Coerce the confirm_type to a ConfirmType enum."""
        if isinstance(confirm_type, ConfirmType):
            return confirm_type
        elif isinstance(confirm_type, str):
            return ConfirmType(confirm_type)
        return ConfirmType(confirm_type)

    async def _confirm(self) -> bool:
        """Confirm the action with the user."""
        match self.confirm_type:
            case ConfirmType.YES_NO:
                return await confirm_async(
                    self.message,
                    prefix="❓ ",
                    suffix=" [Y/n] > ",
                    session=self.prompt_session,
                )
            case ConfirmType.YES_NO_CANCEL:
                answer = await self.prompt_session.prompt_async(
                    f"❓ {self.message} ([Y]es, [N]o, or [C]ancel to abort): ",
                    validator=words_validator(["Y", "N", "C"]),
                )
                if answer.upper() == "C":
                    raise CancelSignal(f"Action '{self.name}' was cancelled by the user.")
                return answer.upper() == "Y"
            case ConfirmType.TYPE_WORD:
                answer = await self.prompt_session.prompt_async(
                    f"❓ {self.message} (type '{self.word}' to confirm or N/n): ",
                    validator=word_validator(self.word),
                )
                return answer.upper().strip() != "N"
            case ConfirmType.YES_CANCEL:
                answer = await confirm_async(
                    self.message,
                    prefix="❓ ",
                    suffix=" [Y/n] > ",
                    session=self.prompt_session,
                )
                if not answer:
                    raise CancelSignal(f"Action '{self.name}' was cancelled by the user.")
                return answer
            case ConfirmType.OK_CANCEL:
                answer = await self.prompt_session.prompt_async(
                    f"❓ {self.message} ([O]k to continue, [C]ancel to abort): ",
                    validator=words_validator(["O", "C"]),
                )
                if answer.upper() == "C":
                    raise CancelSignal(f"Action '{self.name}' was cancelled by the user.")
                return answer.upper() == "O"
            case _:
                raise ValueError(f"Unknown confirm_type: {self.confirm_type}")

    def get_infer_target(self) -> tuple[None, None]:
        return None, None

    async def _run(self, *args, **kwargs) -> Any:
        combined_kwargs = self._maybe_inject_last_result(kwargs)
        context = ExecutionContext(
            name=self.name, args=args, kwargs=combined_kwargs, action=self
        )
        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)
            if (
                not self.confirm
                or self.options_manager
                and not should_prompt_user(
                    confirm=self.confirm, options=self.options_manager
                )
            ):
                logger.debug(
                    "Skipping confirmation for action '%s' as 'confirm' is False or options manager indicates no prompt.",
                    self.name,
                )
                if self.return_last_result:
                    result = combined_kwargs[self.inject_into]
                else:
                    result = True
            else:
                answer = await self._confirm()
                if self.return_last_result and answer:
                    result = combined_kwargs[self.inject_into]
                else:
                    result = answer
            logger.debug("Action '%s' confirmed with result: %s", self.name, result)
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

    async def preview(self, parent: Tree | None = None) -> None:
        tree = (
            Tree(
                f"[{OneColors.CYAN_b}]ConfirmAction[/]: {self.name}",
                guide_style=OneColors.BLUE_b,
            )
            if not parent
            else parent.add(f"[{OneColors.CYAN_b}]ConfirmAction[/]: {self.name}")
        )
        tree.add(f"[bold]Message:[/] {self.message}")
        tree.add(f"[bold]Type:[/] {self.confirm_type.value}")
        tree.add(f"[bold]Prompt Required:[/] {'Yes' if self.confirm else 'No'}")
        if self.confirm_type == ConfirmType.TYPE_WORD:
            tree.add(f"[bold]Confirmation Word:[/] {self.word}")
        if parent is None:
            self.console.print(tree)

    def __str__(self) -> str:
        return (
            f"ConfirmAction(name={self.name}, message={self.message}, "
            f"confirm_type={self.confirm_type})"
        )
