# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""user_input_action.py"""
from prompt_toolkit import PromptSession
from prompt_toolkit.validation import Validator
from rich.tree import Tree

from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.themes.colors import OneColors


class UserInputAction(BaseAction):
    """
    Prompts the user for input via PromptSession and returns the result.

    Args:
        name (str): Action name.
        prompt_text (str): Prompt text (can include '{last_result}' for interpolation).
        validator (Validator, optional): Prompt Toolkit validator.
        prompt_session (PromptSession, optional): Reusable prompt session.
        inject_last_result (bool): Whether to inject last_result into prompt.
        inject_into (str): Key to use for injection (default: 'last_result').
    """

    def __init__(
        self,
        name: str,
        *,
        prompt_text: str = "Input > ",
        default_text: str = "",
        validator: Validator | None = None,
        prompt_session: PromptSession | None = None,
        inject_last_result: bool = False,
    ):
        super().__init__(
            name=name,
            inject_last_result=inject_last_result,
        )
        self.prompt_text = prompt_text
        self.validator = validator
        self.prompt_session = prompt_session or PromptSession()
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

            prompt_text = self.prompt_text
            if self.inject_last_result and self.last_result:
                prompt_text = prompt_text.format(last_result=self.last_result)

            answer = await self.prompt_session.prompt_async(
                prompt_text,
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

        prompt_text = (
            self.prompt_text.replace("{last_result}", "<last_result>")
            if "{last_result}" in self.prompt_text
            else self.prompt_text
        )
        tree.add(f"[dim]Prompt:[/] {prompt_text}")
        if self.validator:
            tree.add("[dim]Validator:[/] Yes")
        if not parent:
            self.console.print(tree)

    def __str__(self):
        return f"UserInputAction(name={self.name!r}, prompt={self.prompt!r})"
