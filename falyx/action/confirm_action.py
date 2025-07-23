# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines `ConfirmAction`, a Falyx Action that prompts the user for confirmation
before continuing execution.

`ConfirmAction` supports a wide range of confirmation strategies, including:
- Yes/No-style prompts
- OK/Cancel dialogs
- Typed confirmation (e.g., "CONFIRM" or "DELETE")
- Acknowledge-only flows

It is useful for adding safety gates, user-driven approval steps, or destructive
operation guards in CLI workflows. This Action supports both interactive use and
non-interactive (headless) behavior via `never_prompt`, as well as full hook lifecycle
integration and optional result passthrough.

Key Features:
- Supports all common confirmation types (see `ConfirmType`)
- Integrates with `PromptSession` for prompt_toolkit-based UX
- Configurable fallback word validation and behavior on cancel
- Can return the injected `last_result` instead of a boolean
- Fully compatible with Falyx hooks, preview, and result injection

Use Cases:
- Safety checks before deleting, pushing, or overwriting resources
- Gatekeeping interactive workflows
- Validating irreversible or sensitive operations

Example:
    ConfirmAction(
        name="ConfirmDeploy",
        message="Are you sure you want to deploy to production?",
        confirm_type="yes_no_cancel",
    )

Raises:
- `CancelSignal`: When the user chooses to abort the action
- `ValueError`: If an invalid `confirm_type` is provided
"""

from __future__ import annotations

from typing import Any

from prompt_toolkit import PromptSession
from rich.tree import Tree

from falyx.action.action_types import ConfirmType
from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.logger import logger
from falyx.prompt_utils import (
    confirm_async,
    rich_text_to_prompt_text,
    should_prompt_user,
)
from falyx.signals import CancelSignal
from falyx.themes import OneColors
from falyx.validators import word_validator, words_validator


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
        name (str): Name of the action. Used for logging and debugging.
        prompt_message (str): The confirmation message to display.
        confirm_type (ConfirmType | str): The type of confirmation to use.
            Options include YES_NO, YES_CANCEL, YES_NO_CANCEL, TYPE_WORD, and OK_CANCEL.
        prompt_session (PromptSession | None): The session to use for input.
        confirm (bool): Whether to prompt the user for confirmation.
        word (str): The word to type for TYPE_WORD confirmation.
        return_last_result (bool): Whether to return the last result of the action
                                   instead of a boolean.
    """

    def __init__(
        self,
        name: str,
        prompt_message: str = "Confirm?",
        confirm_type: ConfirmType | str = ConfirmType.YES_NO,
        prompt_session: PromptSession | None = None,
        never_prompt: bool = False,
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
            never_prompt=never_prompt,
        )
        self.prompt_message = prompt_message
        self.confirm_type = ConfirmType(confirm_type)
        self.prompt_session = prompt_session or PromptSession(
            interrupt_exception=CancelSignal
        )
        self.word = word
        self.return_last_result = return_last_result

    async def _confirm(self) -> bool:
        """Confirm the action with the user."""
        match self.confirm_type:
            case ConfirmType.YES_NO:
                return await confirm_async(
                    rich_text_to_prompt_text(self.prompt_message),
                    suffix=rich_text_to_prompt_text(
                        f" [[{OneColors.GREEN_b}]Y[/]]es, "
                        f"[[{OneColors.DARK_RED_b}]N[/]]o > "
                    ),
                    session=self.prompt_session,
                )
            case ConfirmType.YES_NO_CANCEL:
                error_message = "Enter 'Y', 'y' to confirm, 'N', 'n' to decline, or 'C', 'c' to abort."
                answer = await self.prompt_session.prompt_async(
                    rich_text_to_prompt_text(
                        f"❓ {self.prompt_message} [[{OneColors.GREEN_b}]Y[/]]es, "
                        f"[[{OneColors.DARK_YELLOW_b}]N[/]]o, "
                        f"or [[{OneColors.DARK_RED_b}]C[/]]ancel to abort > "
                    ),
                    validator=words_validator(
                        ["Y", "N", "C"], error_message=error_message
                    ),
                )
                if answer.upper() == "C":
                    raise CancelSignal(f"Action '{self.name}' was cancelled by the user.")
                return answer.upper() == "Y"
            case ConfirmType.TYPE_WORD:
                answer = await self.prompt_session.prompt_async(
                    rich_text_to_prompt_text(
                        f"❓ {self.prompt_message} [[{OneColors.GREEN_b}]{self.word.upper()}[/]] "
                        f"to confirm or [[{OneColors.DARK_RED}]N[/{OneColors.DARK_RED}]] > "
                    ),
                    validator=word_validator(self.word),
                )
                return answer.upper().strip() != "N"
            case ConfirmType.TYPE_WORD_CANCEL:
                answer = await self.prompt_session.prompt_async(
                    rich_text_to_prompt_text(
                        f"❓ {self.prompt_message} [[{OneColors.GREEN_b}]{self.word.upper()}[/]] "
                        f"to confirm or [[{OneColors.DARK_RED}]N[/{OneColors.DARK_RED}]] > "
                    ),
                    validator=word_validator(self.word),
                )
                if answer.upper().strip() == "N":
                    raise CancelSignal(f"Action '{self.name}' was cancelled by the user.")
                return answer.upper().strip() == self.word.upper().strip()
            case ConfirmType.YES_CANCEL:
                answer = await confirm_async(
                    rich_text_to_prompt_text(self.prompt_message),
                    suffix=rich_text_to_prompt_text(
                        f" [[{OneColors.GREEN_b}]Y[/]]es, "
                        f"[[{OneColors.DARK_RED_b}]N[/]]o > "
                    ),
                    session=self.prompt_session,
                )
                if not answer:
                    raise CancelSignal(f"Action '{self.name}' was cancelled by the user.")
                return answer
            case ConfirmType.OK_CANCEL:
                error_message = "Enter 'O', 'o' to confirm or 'C', 'c' to abort."
                answer = await self.prompt_session.prompt_async(
                    rich_text_to_prompt_text(
                        f"❓ {self.prompt_message} [[{OneColors.GREEN_b}]O[/]]k to confirm, "
                        f"[[{OneColors.DARK_RED}]C[/]]ancel to abort > "
                    ),
                    validator=words_validator(["O", "C"], error_message=error_message),
                )
                if answer.upper() == "C":
                    raise CancelSignal(f"Action '{self.name}' was cancelled by the user.")
                return answer.upper() == "O"
            case ConfirmType.ACKNOWLEDGE:
                answer = await self.prompt_session.prompt_async(
                    rich_text_to_prompt_text(
                        f"❓ {self.prompt_message} [[{OneColors.CYAN_b}]A[/]]cknowledge > "
                    ),
                    validator=word_validator("A"),
                )
                return answer.upper().strip() == "A"
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
                self.never_prompt
                or self.options_manager
                and not should_prompt_user(confirm=True, options=self.options_manager)
            ):
                logger.debug(
                    "Skipping confirmation for '%s' due to never_prompt or options_manager settings.",
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
        tree.add(f"[bold]Message:[/] {self.prompt_message}")
        tree.add(f"[bold]Type:[/] {self.confirm_type.value}")
        tree.add(f"[bold]Prompt Required:[/] {'No' if self.never_prompt else 'Yes'}")
        if self.confirm_type in (ConfirmType.TYPE_WORD, ConfirmType.TYPE_WORD_CANCEL):
            tree.add(f"[bold]Confirmation Word:[/] {self.word}")
        if parent is None:
            self.console.print(tree)

    def __str__(self) -> str:
        return (
            f"ConfirmAction(name={self.name}, message={self.prompt_message}, "
            f"confirm_type={self.confirm_type}, return_last_result={self.return_last_result})"
        )
