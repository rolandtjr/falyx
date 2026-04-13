# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Standalone command runner for the Falyx CLI framework.

This module defines `CommandRunner`, a developer-facing convenience wrapper for
executing a single `Command` outside the full `Falyx` runtime.

`CommandRunner` is designed for programmatic and standalone command execution
where command lookup, menu interaction, and root CLI parsing are not needed.
It provides a small, focused API that:

- owns a single `Command`
- ensures the command and parser share a consistent `OptionsManager`
- delegates shared execution behavior to `CommandExecutor`
- supports both wrapping an existing `Command` and building one from raw
  constructor-style arguments

Responsibilities:
    - Hold a single resolved `Command` for repeated execution
    - Normalize runtime dependencies such as `OptionsManager`, `HookManager`,
      and `Console`
    - Resolve command arguments from raw argv-style input
    - Delegate execution to `CommandExecutor` for shared outer lifecycle
      handling

Design Notes:
    - `CommandRunner` is intentionally narrower than `Falyx`.
      It does not resolve commands by name, render menus, or manage built-ins.
    - `CommandExecutor` remains the shared execution core.
      `CommandRunner` exists as a convenience layer for developer-facing and
      standalone use cases.
    - `Command` still owns command-local behavior such as confirmation,
      command hook execution, and delegation to the underlying `Action`.

Typical Usage:
    runner = CommandRunner.from_command(existing_command)
    result = await runner.run(["--region", "us-east"])

    #!/usr/bin/env python
    import asyncio
    runner = CommandRunner.build(
        key="D",
        description="Deploy",
        action=deploy,
    )
    result = asyncio.run(runner.cli())
    $ ./deploy.py --region us-east
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any, Callable

from rich.console import Console

from falyx.action import BaseAction
from falyx.command import Command
from falyx.command_executor import CommandExecutor
from falyx.console import console as falyx_console
from falyx.exceptions import CommandArgumentError, FalyxError, NotAFalyxError
from falyx.execution_option import ExecutionOption
from falyx.hook_manager import HookManager
from falyx.logger import logger
from falyx.options_manager import OptionsManager
from falyx.parser.command_argument_parser import CommandArgumentParser
from falyx.protocols import ArgParserProtocol
from falyx.retry import RetryPolicy
from falyx.signals import BackSignal, CancelSignal, HelpSignal, QuitSignal
from falyx.themes import OneColors


class CommandRunner:
    """Run a single Falyx command outside the full Falyx application runtime.

    `CommandRunner` is a lightweight wrapper around a single `Command` plus a
    `CommandExecutor`. It is intended for standalone execution, testing, and
    developer-facing programmatic usage where command resolution has already
    happened or is unnecessary.

    This class is responsible for:
        - storing the bound `Command`
        - providing a shared `OptionsManager` to the command and its parser
        - exposing a simple `run()` method that accepts argv-style input
        - delegating shared execution behavior to `CommandExecutor`

    Attributes:
        command (Command): The command executed by this runner.
        options (OptionsManager): Shared options manager used by the command,
            parser, and executor.
        runner_hooks (HookManager): Executor-level hooks used during execution.
        console (Console): Rich console used for user-facing output.
        executor (CommandExecutor): Shared execution engine used to run the
            bound command.
    """

    def __init__(
        self,
        command: Command,
        *,
        options: OptionsManager | None = None,
        runner_hooks: HookManager | None = None,
        console: Console | None = None,
    ) -> None:
        """Initialize a `CommandRunner` for a single command.

        The runner ensures that the bound command, its argument parser, and the
        internal `CommandExecutor` all share the same `OptionsManager` and runtime
        dependencies.

        Args:
            command (Command): The command to execute.
            options (OptionsManager | None): Optional shared options manager. If
                omitted, a new `OptionsManager` is created.
            runner_hooks (HookManager | None): Optional executor-level hook manager. If
                omitted, a new `HookManager` is created.
            console (Console | None): Optional Rich console for output. If omitted,
                the default Falyx console is used.
        """
        self.command = command
        self.options = self._get_options(options)
        self.runner_hooks = self._get_hooks(runner_hooks)
        self.console = self._get_console(console)
        self.command.options_manager = self.options
        if isinstance(self.command.arg_parser, CommandArgumentParser):
            self.command.arg_parser.set_options_manager(self.options)
        self.executor = CommandExecutor(
            options=self.options,
            hooks=self.runner_hooks,
            console=self.console,
        )
        self.options.from_mapping(values={}, namespace_name="execution")

    def _get_console(self, console) -> Console:
        if console is None:
            return falyx_console
        elif isinstance(console, Console):
            return console
        else:
            raise NotAFalyxError("console must be an instance of rich.Console or None.")

    def _get_options(self, options) -> OptionsManager:
        if options is None:
            return OptionsManager()
        elif isinstance(options, OptionsManager):
            return options
        else:
            raise NotAFalyxError("options must be an instance of OptionsManager or None.")

    def _get_hooks(self, hooks) -> HookManager:
        if hooks is None:
            return HookManager()
        elif isinstance(hooks, HookManager):
            return hooks
        else:
            raise NotAFalyxError("hooks must be an instance of HookManager or None.")

    async def run(
        self,
        argv: list[str] | str | None = None,
        raise_on_error: bool = True,
        wrap_errors: bool = False,
        summary_last_result: bool = False,
    ) -> Any:
        """Resolve arguments and execute the bound command.

        This method is the primary execution entrypoint for `CommandRunner`. It
        accepts raw argv-style tokens, resolves them into positional arguments,
        keyword arguments, and execution arguments via `Command.resolve_args()`,
        then delegates execution to the internal `CommandExecutor`.

        Args:
            argv (list[str] | str | None): Optional argv-style argument tokens or
                string (uses `shlex.split()` if a string is provided). If omitted,
                `sys.argv[1:]` is used.

        Returns:
            Any: The result returned by the bound command.

        Raises:
            Exception: Propagates any execution error surfaced by the underlying
                `CommandExecutor` or command execution path.
        """
        argv = sys.argv[1:] if argv is None else argv
        args, kwargs, execution_args = await self.command.resolve_args(argv)
        logger.debug(
            "Executing command '%s' with args=%s, kwargs=%s, execution_args=%s",
            self.command.description,
            args,
            kwargs,
            execution_args,
        )
        return await self.executor.execute(
            command=self.command,
            args=args,
            kwargs=kwargs,
            execution_args=execution_args,
            raise_on_error=raise_on_error,
            wrap_errors=wrap_errors,
            summary_last_result=summary_last_result,
        )

    async def cli(
        self,
        argv: list[str] | str | None = None,
        summary_last_result: bool = False,
    ) -> Any:
        """Run the bound command as a shell-oriented CLI entrypoint.

        This method wraps `run()` with command-line specific behavior. It executes the
        bound command using raw argv-style input, then translates framework signals and
        execution failures into user-facing console output and process exit codes.

        Unlike `run()`, this method is intended for direct CLI usage rather than
        programmatic integration. It may terminate the current process via `sys.exit()`.

        Behavior:
            - Delegates normal execution to `run()`
            - Exits with status code `0` when help output is requested
            - Exits with status code `2` for command argument or usage errors
            - Exits with status code `1` for execution failures and non-success control
            flow such as cancellation or back-navigation
            - Exits with status code `130` for quit/interrupt-style termination

        Args:
            argv (list[str] | str | None): Optional argv-style argument tokens or string
                (uses `shlex.split()` if a string is provided). If omitted, `sys.argv[1:]`
                is used by `run()`.
            summary_last_result (bool): Whether summary output should include the last
                recorded result when summary reporting is enabled.

        Returns:
            Any: The result returned by the bound command when execution completes
            successfully.

        Raises:
            SystemExit: Always raised for handled CLI exit paths, including help,
                argument errors, cancellations, and execution failures.

        Notes:
            - This method is intentionally shell-facing and should be used in
            script entrypoints such as `asyncio.run(runner.cli())`.
            - For programmatic use, prefer `run()`, which preserves normal Python
            exception behavior and does not call `sys.exit()`.
        """
        try:
            return await self.run(
                argv=argv,
                raise_on_error=False,
                wrap_errors=True,
                summary_last_result=summary_last_result,
            )
        except HelpSignal:
            sys.exit(0)
        except CommandArgumentError as error:
            self.command.render_help()
            self.console.print(f"[{OneColors.DARK_RED}]❌ ['{self.command.key}'] {error}")
            sys.exit(2)
        except FalyxError as error:
            self.console.print(f"[{OneColors.DARK_RED}]❌ Error: {error}[/]")
            sys.exit(1)
        except QuitSignal:
            logger.info("[QuitSignal]. <- Exiting run.")
            sys.exit(130)
        except BackSignal:
            logger.info("[BackSignal]. <- Exiting run.")
            sys.exit(1)
        except CancelSignal:
            logger.info("[CancelSignal]. <- Exiting run.")
            sys.exit(1)
        except asyncio.CancelledError:
            logger.info("[asyncio.CancelledError]. <- Exiting run.")
            sys.exit(1)

    @classmethod
    def from_command(
        cls,
        command: Command,
        *,
        runner_hooks: HookManager | None = None,
        options: OptionsManager | None = None,
        console: Console | None = None,
    ) -> CommandRunner:
        """Create a `CommandRunner` from an existing `Command` instance.

        This factory is useful when a command has already been defined elsewhere
        and should be exposed through the standalone runner interface without
        rebuilding it.

        Args:
            command (Command): Existing command instance to wrap.
            runner_hooks (HookManager | None): Optional executor-level hook manager
                for the runner.
            options (OptionsManager | None): Optional shared options manager.
            console (Console | None): Optional Rich console for output.

        Returns:
            CommandRunner: A runner bound to the provided command.

        Raises:
            NotAFalyxError: If `runner_hooks` is provided but is not a
                `HookManager` instance.
        """
        if not isinstance(command, Command):
            raise NotAFalyxError("command must be an instance of Command.")
        if runner_hooks and not isinstance(runner_hooks, HookManager):
            raise NotAFalyxError("runner_hooks must be an instance of HookManager.")
        return cls(
            command=command,
            options=options,
            runner_hooks=runner_hooks,
            console=console,
        )

    @classmethod
    def build(
        cls,
        key: str,
        description: str,
        action: BaseAction | Callable[..., Any],
        *,
        runner_hooks: HookManager | None = None,
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
        hidden: bool = False,
        aliases: list[str] | None = None,
        help_text: str = "",
        help_epilog: str = "",
        style: str = OneColors.WHITE,
        confirm: bool = False,
        confirm_message: str = "Are you sure?",
        preview_before_confirm: bool = True,
        spinner: bool = False,
        spinner_message: str = "Processing...",
        spinner_type: str = "dots",
        spinner_style: str = OneColors.CYAN,
        spinner_speed: float = 1.0,
        options: OptionsManager | None = None,
        command_hooks: HookManager | None = None,
        before_hooks: list[Callable] | None = None,
        success_hooks: list[Callable] | None = None,
        error_hooks: list[Callable] | None = None,
        after_hooks: list[Callable] | None = None,
        teardown_hooks: list[Callable] | None = None,
        tags: list[str] | None = None,
        logging_hooks: bool = False,
        retry: bool = False,
        retry_all: bool = False,
        retry_policy: RetryPolicy | None = None,
        arg_parser: CommandArgumentParser | None = None,
        arguments: list[dict[str, Any]] | None = None,
        argument_config: Callable[[CommandArgumentParser], None] | None = None,
        execution_options: list[ExecutionOption | str] | None = None,
        custom_parser: ArgParserProtocol | None = None,
        custom_help: Callable[[], str | None] | None = None,
        auto_args: bool = True,
        arg_metadata: dict[str, str | dict[str, Any]] | None = None,
        simple_help_signature: bool = False,
        ignore_in_history: bool = False,
        console: Console | None = None,
    ) -> CommandRunner:
        """Build a `Command` and wrap it in a `CommandRunner`.

        This factory is a convenience constructor for standalone usage. It mirrors
        the high-level command-building API by creating a configured `Command`
        through `Command.build()` and then returning a `CommandRunner` bound to it.

        Args:
            key (str): Primary key used to invoke the command.
            description (str): Short description of the command.
            action (BaseAction | Callable[..., Any]): Underlying execution logic for
                the command.
            runner_hooks (HookManager | None): Optional executor-level hooks for the
                runner.
            args (tuple): Static positional arguments applied to the command.
            kwargs (dict[str, Any] | None): Static keyword arguments applied to the
                command.
            hidden (bool): Whether the command should be hidden from menu displays.
            aliases (list[str] | None): Optional alternate invocation names.
            help_text (str): Help text shown in command help output.
            help_epilog (str): Additional help text shown after the main help body.
            style (str): Rich style used for rendering the command.
            confirm (bool): Whether confirmation is required before execution.
            confirm_message (str): Confirmation prompt text.
            preview_before_confirm (bool): Whether to preview before confirmation.
            spinner (bool): Whether to enable spinner integration.
            spinner_message (str): Spinner message text.
            spinner_type (str): Spinner animation type.
            spinner_style (str): Spinner style.
            spinner_speed (float): Spinner speed multiplier.
            options (OptionsManager | None): Shared options manager for the command
                and runner.
            command_hooks (HookManager | None): Optional hook manager for the built
                command itself.
            before_hooks (list[Callable] | None): Command hooks registered for the
                `BEFORE` lifecycle stage.
            success_hooks (list[Callable] | None): Command hooks registered for the
                `ON_SUCCESS` lifecycle stage.
            error_hooks (list[Callable] | None): Command hooks registered for the
                `ON_ERROR` lifecycle stage.
            after_hooks (list[Callable] | None): Command hooks registered for the
                `AFTER` lifecycle stage.
            teardown_hooks (list[Callable] | None): Command hooks registered for the
                `ON_TEARDOWN` lifecycle stage.
            tags (list[str] | None): Optional tags used for grouping and filtering.
            logging_hooks (bool): Whether to enable debug hook logging.
            retry (bool): Whether retry behavior is enabled.
            retry_all (bool): Whether retry behavior should be applied recursively.
            retry_policy (RetryPolicy | None): Retry configuration for the command.
            arg_parser (CommandArgumentParser | None): Optional explicit argument
                parser instance.
            arguments (list[dict[str, Any]] | None): Declarative argument
                definitions.
            argument_config (Callable[[CommandArgumentParser], None] | None):
                Callback used to configure the argument parser.
            execution_options (list[ExecutionOption | str] | None): Execution-level
                options to enable for the command.
            custom_parser (ArgParserProtocol | None): Optional custom parser
                implementation.
            custom_help (Callable[[], str | None] | None): Optional custom help
                renderer.
            auto_args (bool): Whether to infer arguments automatically from the
                action signature.
            arg_metadata (dict[str, str | dict[str, Any]] | None): Optional
                metadata used during argument inference.
            simple_help_signature (bool): Whether to use a simplified help
                signature.
            ignore_in_history (bool): Whether to exclude the command from execution
                history tracking.
            console (Console | None): Optional Rich console for output.

        Returns:
            CommandRunner: A runner wrapping the newly built command.

        Raises:
            NotAFalyxError: If `runner_hooks` is provided but is not a
                `HookManager` instance.

        Notes:
            - This method is intended as a standalone convenience factory.
            - Command construction is delegated to `Command.build()` so command
            configuration remains centralized.
        """
        options = options or OptionsManager()
        command = Command.build(
            key=key,
            description=description,
            action=action,
            args=args,
            kwargs=kwargs,
            hidden=hidden,
            aliases=aliases,
            help_text=help_text,
            help_epilog=help_epilog,
            style=style,
            confirm=confirm,
            confirm_message=confirm_message,
            preview_before_confirm=preview_before_confirm,
            spinner=spinner,
            spinner_message=spinner_message,
            spinner_type=spinner_type,
            spinner_style=spinner_style,
            spinner_speed=spinner_speed,
            tags=tags,
            logging_hooks=logging_hooks,
            retry=retry,
            retry_all=retry_all,
            retry_policy=retry_policy,
            options_manager=options,
            hooks=command_hooks,
            before_hooks=before_hooks,
            success_hooks=success_hooks,
            error_hooks=error_hooks,
            after_hooks=after_hooks,
            teardown_hooks=teardown_hooks,
            arg_parser=arg_parser,
            execution_options=execution_options,
            arguments=arguments,
            argument_config=argument_config,
            custom_parser=custom_parser,
            custom_help=custom_help,
            auto_args=auto_args,
            arg_metadata=arg_metadata,
            simple_help_signature=simple_help_signature,
            ignore_in_history=ignore_in_history,
        )

        if runner_hooks and not isinstance(runner_hooks, HookManager):
            raise NotAFalyxError("runner_hooks must be an instance of HookManager.")

        return cls(
            command=command,
            options=options,
            runner_hooks=runner_hooks,
            console=console,
        )
