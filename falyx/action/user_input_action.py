# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines `UserInputAction`, a Falyx Action that prompts the user for input using
Prompt Toolkit and returns the result as a string.

This action is ideal for interactive CLI workflows that require user input mid-pipeline.
It supports dynamic prompt interpolation, prompt validation, default text fallback,
and full lifecycle hook execution.

Key Features:
- Rich Prompt Toolkit integration for input and validation
- Dynamic prompt formatting using `last_result` injection
- Optional `Validator` support for structured input (e.g., emails, numbers)
- Hook lifecycle compatibility (before, on_success, on_error, after, teardown)
- Preview support for introspection or dry-run flows

Use Cases:
- Asking for confirmation text or field input mid-chain
- Injecting user-provided variables into automated pipelines
- Interactive menu or wizard experiences

Example:
    UserInputAction(
        name="GetUsername",
        prompt_message="Enter your username > ",
        validator=Validator.from_callable(lambda s: len(s) > 0),
    )
"""
from prompt_toolkit import PromptSession
from prompt_toolkit.validation import Validator
from rich.tree import Tree

from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.prompt_utils import rich_text_to_prompt_text
from falyx.signals import CancelSignal
from falyx.themes.colors import OneColors


class UserInputAction(BaseAction):
    """
    Prompts the user for textual input and returns their response.

    `UserInputAction` uses Prompt Toolkit to gather input with optional validation,
    lifecycle hook compatibility, and support for default text. If `inject_last_result`
    is enabled, the prompt message can interpolate `{last_result}` dynamically.

    Args:
        name (str): Name of the action (used for introspection and logging).
        prompt_message (str): The prompt message shown to the user.
            Can include `{last_result}` if `inject_last_result=True`.
        default_text (str): Optional default value shown in the prompt.
        validator (Validator | None): Prompt Toolkit validator for input constraints.
        prompt_session (PromptSession | None): Optional custom prompt session.
        inject_last_result (bool): Whether to inject `last_result` into the prompt.
    """

    def __init__(
        self,
        name: str,
        *,
        prompt_message: str = "Input > ",
        default_text: str = "",
        validator: Validator | None = None,
        prompt_session: PromptSession | None = None,
        inject_last_result: bool = False,
    ):
        super().__init__(
            name=name,
            inject_last_result=inject_last_result,
        )
        self.prompt_message = rich_text_to_prompt_text(prompt_message)
        self.validator = validator
        self.prompt_session = prompt_session or PromptSession(
            interrupt_exception=CancelSignal
        )
        self.default_text = default_text

    def get_infer_target(self) -> tuple[None, None]:
        return None, None

    async def _run(self, *args, **kwargs) -> str:
        context = ExecutionContext(
            name=self.name,
            args=args,
            kwargs=kwargs,
            action=self,
        )
        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)

            prompt_message = self.prompt_message
            if self.inject_last_result and self.last_result:
                prompt_message = prompt_message.format(last_result=self.last_result)

            answer = await self.prompt_session.prompt_async(
                prompt_message,
                validator=self.validator,
                default=kwargs.get("default_text", self.default_text),
            )
            context.result = answer
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return answer
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
        label = f"[{OneColors.MAGENTA}]⌨ UserInputAction[/] '{self.name}'"
        tree = parent.add(label) if parent else Tree(label)

        prompt_message = (
            self.prompt_message.replace("{last_result}", "<last_result>")
            if "{last_result}" in self.prompt_message
            else self.prompt_message
        )
        tree.add(f"[dim]Prompt:[/] {prompt_message}")
        if self.validator:
            tree.add("[dim]Validator:[/] Yes")
        if not parent:
            self.console.print(tree)

    def __str__(self):
        return f"UserInputAction(name={self.name!r}, prompt={self.prompt!r})"
