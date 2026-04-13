# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Shared command execution engine for the Falyx CLI framework.

This module defines `CommandExecutor`, a low-level execution service responsible
for running already-resolved `Command` objects with a consistent outer lifecycle.

`CommandExecutor` sits between higher-level orchestration layers (such as
`Falyx.execute_command()` or `CommandRunner.run()`) and the command itself.
It does not perform command lookup or argument parsing. Instead, it accepts a
resolved `Command` plus prepared `args`, `kwargs`, and `execution_args`, then
applies executor-level behavior around the command invocation.

Responsibilities:
    - Apply execution-scoped runtime overrides such as confirmation flags
    - Apply retry overrides from execution arguments
    - Trigger executor-level lifecycle hooks
    - Create and manage an outer `ExecutionContext`
    - Delegate actual invocation to the resolved `Command`
    - Handle interruption and failure policies
    - Optionally print execution summaries via `ExecutionRegistry`

Execution Model:
    1. A command is resolved and its arguments are prepared elsewhere.
    2. Retry and execution-option overrides are derived from `execution_args`.
    3. An outer `ExecutionContext` is created for executor-level tracking.
    4. Executor hooks are triggered around the command invocation.
    5. The command is executed inside an `OptionsManager.override_namespace()`
       context for scoped runtime overrides.
    6. Errors are either surfaced, wrapped, or rendered depending on the
       configured execution policy.
    7. Optional summary output is emitted after execution completes.

Design Notes:
    - `CommandExecutor` is intentionally narrower in scope than `Falyx`.
      It does not resolve commands, parse raw CLI text, or manage menu state.
    - `Command` still owns command-local behavior such as confirmation,
      command hooks, and delegation to the underlying `Action`.
    - This module exists to centralize shared execution behavior and reduce
      duplication across Falyx runtime entrypoints.

Typical Usage:
    executor = CommandExecutor(options=options, hooks=hooks, console=console)
    result = await executor.execute(
        command=command,
        args=args,
        kwargs=kwargs,
        execution_args=execution_args,
    )
"""
from __future__ import annotations

from typing import Any

from rich.console import Console

from falyx.action import Action
from falyx.command import Command
from falyx.context import ExecutionContext
from falyx.exceptions import FalyxError
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookManager, HookType
from falyx.logger import logger
from falyx.options_manager import OptionsManager
from falyx.themes import OneColors


class CommandExecutor:
    """Execute resolved Falyx commands with shared outer lifecycle handling.

    `CommandExecutor` provides a reusable execution service for running a
    `Command` after command resolution and argument parsing have already been
    completed.

    This class is intended to be shared by higher-level entrypoints such as
    `Falyx` and `CommandRunner`. It centralizes the outer execution flow so
    command execution semantics remain consistent across menu-driven and
    programmatic use cases.

    Responsibilities:
        - Apply retry overrides from execution arguments
        - Apply scoped runtime overrides using `OptionsManager`
        - Trigger executor-level hooks before and after command execution
        - Create and manage an executor-level `ExecutionContext`
        - Render execution errors to the configured console
        - Control whether errors are raised, wrapped, or suppressed
        - Emit optional execution summaries

    Attributes:
        options (OptionsManager): Shared options manager used to apply scoped
            execution overrides.
        hooks (HookManager): Hook manager for executor-level lifecycle hooks.
        console (Console): Rich console used for user-facing error output.
    """

    def __init__(
        self,
        *,
        options: OptionsManager,
        hooks: HookManager,
        console: Console,
    ) -> None:
        self.options = options
        self.hooks = hooks
        self.console = console

    def _debug_hooks(self, command: Command) -> None:
        """Log executor-level and command-level hook registrations for debugging.

        This helper is used to surface the currently registered hooks on both the
        executor and the resolved command before execution begins.

        Args:
            command (Command): The command about to be executed.
        """
        logger.debug("Executor hooks:\n%s", str(self.hooks))
        logger.debug("['%s'] hooks:\n%s", command.key, str(command.hooks))

    def _apply_retry_overrides(
        self,
        command: Command,
        execution_args: dict[str, Any],
    ) -> None:
        """Apply retry-related execution overrides to the command.

        This method inspects execution-level retry options and updates the
        command's retry policy in place when overrides are provided. If the
        command's underlying action is an `Action`, the updated retry policy is
        propagated to that action as well.

        Args:
            command (Command): The command whose retry policy may be updated.
            execution_args (dict[str, Any]): Execution-level arguments that may
                contain retry overrides such as `retries`, `retry_delay`, and
                `retry_backoff`.

        Notes:
            - If no retry-related overrides are provided, this method does nothing.
            - If the command action is not an `Action`, a warning is logged and the
            command-level retry policy is updated without propagating it further.
        """
        retries = execution_args.get("retries", 0)
        retry_delay = execution_args.get("retry_delay", 0.0)
        retry_backoff = execution_args.get("retry_backoff", 0.0)

        logger.debug(
            "[_apply_retry_overrides]: retries=%s, retry_delay=%s, retry_backoff=%s",
            retries,
            retry_delay,
            retry_backoff,
        )
        if not retries and not retry_delay and not retry_backoff:
            return

        command.retry_policy.enabled = True
        if retries:
            command.retry_policy.max_retries = retries
        if retry_delay:
            command.retry_policy.delay = retry_delay
        if retry_backoff:
            command.retry_policy.backoff = retry_backoff

        if isinstance(command.action, Action):
            command.action.set_retry_policy(command.retry_policy)
        else:
            logger.warning(
                "[%s] Retry requested, but action is not an Action instance.",
                command.description,
            )

    def _execution_option_overrides(
        self,
        execution_args: dict[str, Any],
    ) -> dict[str, Any]:
        """Build scoped option overrides from execution arguments.

        This method extracts execution-only runtime flags that should be applied
        through the `OptionsManager` during command execution.

        Args:
            execution_args (dict[str, Any]): Execution-level arguments returned
                from command argument resolution.

        Returns:
            dict[str, Any]: Mapping of option names to temporary execution-scoped
            override values.
        """
        return {
            "force_confirm": execution_args.get("force_confirm", False),
            "skip_confirm": execution_args.get("skip_confirm", False),
        }

    async def _handle_action_error(
        self, selected_command: Command, error: Exception
    ) -> None:
        """Render and log a command execution error.

        This helper logs the full exception details for debugging and prints a
        user-facing error message to the configured console.

        Args:
            selected_command (Command): The command that failed.
            error (Exception): The exception raised during command execution.
        """
        logger.debug(
            "[%s] '%s' failed with error: %s",
            selected_command.key,
            selected_command.description,
            error,
            exc_info=True,
        )
        self.console.print(
            f"[{OneColors.DARK_RED}]An error occurred while executing "
            f"{selected_command.description}:[/] {error}"
        )

    async def execute(
        self,
        *,
        command: Command,
        args: tuple,
        kwargs: dict[str, Any],
        execution_args: dict[str, Any],
        raise_on_error: bool = True,
        wrap_errors: bool = False,
        summary_last_result: bool = False,
    ) -> Any:
        """Execute a resolved command with executor-level lifecycle management.

        This method is the primary entrypoint of `CommandExecutor`. It accepts an
        already-resolved `Command` and its prepared execution inputs, then applies
        shared outer execution behavior around the command invocation.

        Execution Flow:
            1. Log currently registered hooks for debugging.
            2. Apply retry overrides from `execution_args`.
            3. Derive scoped runtime overrides for the execution namespace.
            4. Create and start an outer `ExecutionContext`.
            5. Trigger executor-level `BEFORE` hooks.
            6. Execute the command inside an execution-scoped options override
            context.
            7. Trigger executor-level `SUCCESS` or `ERROR` hooks.
            8. Trigger `AFTER` and `ON_TEARDOWN` hooks.
            9. Optionally print an execution summary.

        Args:
            command (Command): The resolved command to execute.
            args (tuple): Positional arguments to pass to the command.
            kwargs (dict[str, Any]): Keyword arguments to pass to the command.
            execution_args (dict[str, Any]): Execution-only arguments that affect
                runtime behavior, such as retry or confirmation overrides.
            raise_on_error (bool): Whether execution errors should be re-raised
                after handling.
            wrap_errors (bool): Whether handled errors should be wrapped in a
                `FalyxError` before being raised.
            summary_last_result (bool): Whether summary output should only have the
                last recorded result when summary reporting is enabled.

        Returns:
            Any: The result returned by the command, or any recovered result
            attached to the execution context.

        Raises:
            KeyboardInterrupt: If execution is interrupted by the user and
                `raise_on_error` is True and `wrap_errors` is False.
            EOFError: If execution receives EOF interruption and `raise_on_error`
                is True and `wrap_errors` is False.
            FalyxError: If `wrap_errors` is True and execution is interrupted or
                fails.
            Exception: Re-raises the underlying execution error when
                `raise_on_error` is True and `wrap_errors` is False.

        Notes:
            - This method assumes the command has already been resolved and its
            arguments have already been parsed.
            - Command-local behavior, such as confirmation prompts and command hook
            execution, remains the responsibility of `Command.__call__()`.
            - Summary output is only emitted when the `summary` execution option is
            present in `execution_args`.
        """
        self._debug_hooks(command)
        self._apply_retry_overrides(command, execution_args)
        overrides = self._execution_option_overrides(execution_args)

        context = ExecutionContext(
            name=command.description,
            args=args,
            kwargs=kwargs,
            action=command,
        )
        logger.info(
            "[execute] Starting execution of '%s' with args: %s, kwargs: %s",
            command.description,
            args,
            kwargs,
        )
        context.start_timer()

        try:
            await self.hooks.trigger(HookType.BEFORE, context)
            with self.options.override_namespace(
                overrides=overrides,
                namespace_name="execution",
            ):
                result = await command(*args, **kwargs)
            context.result = result
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
        except (KeyboardInterrupt, EOFError) as error:
            logger.info(
                "[execute] '%s' interrupted by user.",
                command.description,
            )
            if wrap_errors:
                raise FalyxError(
                    f"[execute] ⚠️ '{command.description}' interrupted by user."
                ) from error
            if raise_on_error:
                raise error
        except Exception as error:
            context.exception = error
            await self.hooks.trigger(HookType.ON_ERROR, context)
            await self._handle_action_error(command, error)
            if wrap_errors:
                raise FalyxError(
                    f"[execute] '{command.description}' failed: {error}"
                ) from error
            if raise_on_error:
                raise error
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
        if execution_args.get("summary") and summary_last_result:
            er.summary(last_result=True)
        elif execution_args.get("summary"):
            er.summary()
        return context.result
