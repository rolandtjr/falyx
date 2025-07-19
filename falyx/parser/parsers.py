# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Provides the argument parser infrastructure for the Falyx CLI.

This module defines the `FalyxParsers` dataclass and related utilities for building
structured CLI interfaces with argparse. It supports top-level CLI commands like
`run`, `run-all`, `preview`, `list`, and `version`, and integrates seamlessly with
registered `Command` objects for dynamic help, usage generation, and argument handling.

Key Components:
- `FalyxParsers`: Container for all CLI subparsers.
- `get_arg_parsers()`: Factory for generating full parser suite.
- `get_root_parser()`: Creates the root-level CLI parser with global options.
- `get_subparsers()`: Helper to attach subcommand parsers to the root parser.

Used internally by the Falyx CLI `run()` entry point to parse arguments and route
execution across commands and workflows.
"""

from argparse import (
    REMAINDER,
    ArgumentParser,
    Namespace,
    RawDescriptionHelpFormatter,
    _SubParsersAction,
)
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from falyx.command import Command


@dataclass
class FalyxParsers:
    """Defines the argument parsers for the Falyx CLI."""

    root: ArgumentParser
    subparsers: _SubParsersAction
    run: ArgumentParser
    run_all: ArgumentParser
    preview: ArgumentParser
    list: ArgumentParser
    version: ArgumentParser

    def parse_args(self, args: Sequence[str] | None = None) -> Namespace:
        """Parse the command line arguments."""
        return self.root.parse_args(args)

    def as_dict(self) -> dict[str, ArgumentParser]:
        """Convert the FalyxParsers instance to a dictionary."""
        return asdict(self)

    def get_parser(self, name: str) -> ArgumentParser | None:
        """Get the parser by name."""
        return self.as_dict().get(name)


def get_root_parser(
    prog: str | None = "falyx",
    usage: str | None = None,
    description: str | None = "Falyx CLI - Run structured async command workflows.",
    epilog: (
        str | None
    ) = "Tip: Use 'falyx run ?[COMMAND]' to preview any command from the CLI.",
    parents: Sequence[ArgumentParser] | None = None,
    prefix_chars: str = "-",
    fromfile_prefix_chars: str | None = None,
    argument_default: Any = None,
    conflict_handler: str = "error",
    add_help: bool = True,
    allow_abbrev: bool = True,
    exit_on_error: bool = True,
) -> ArgumentParser:
    """
    Construct the root-level ArgumentParser for the Falyx CLI.

    This parser handles global arguments shared across subcommands and can serve
    as the base parser for the Falyx CLI or standalone applications. It includes
    options for verbosity, debug logging, and version output.

    Args:
        prog (str | None): Name of the program (e.g., 'falyx').
        usage (str | None): Optional custom usage string.
        description (str | None): Description shown in the CLI help.
        epilog (str | None): Message displayed at the end of help output.
        parents (Sequence[ArgumentParser] | None): Optional parent parsers.
        prefix_chars (str): Characters to denote optional arguments (default: "-").
        fromfile_prefix_chars (str | None): Prefix to indicate argument file input.
        argument_default (Any): Global default value for arguments.
        conflict_handler (str): Strategy to resolve conflicting argument names.
        add_help (bool): Whether to include help (`-h/--help`) in this parser.
        allow_abbrev (bool): Allow abbreviated long options.
        exit_on_error (bool): Exit immediately on error or raise an exception.

    Returns:
        ArgumentParser: The root parser with global options attached.

    Notes:
        ```
        Includes the following arguments:
            --never-prompt       : Run in non-interactive mode.
            -v / --verbose       : Enable debug logging.
            --debug-hooks        : Enable hook lifecycle debug logs.
            --version            : Print the Falyx version.
        ```
    """
    parser = ArgumentParser(
        prog=prog,
        usage=usage,
        description=description,
        epilog=epilog,
        parents=parents if parents else [],
        prefix_chars=prefix_chars,
        fromfile_prefix_chars=fromfile_prefix_chars,
        argument_default=argument_default,
        conflict_handler=conflict_handler,
        add_help=add_help,
        allow_abbrev=allow_abbrev,
        exit_on_error=exit_on_error,
    )
    parser.add_argument(
        "--never-prompt",
        action="store_true",
        help="Run in non-interactive mode with all prompts bypassed.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help=f"Enable debug logging for {prog}."
    )
    parser.add_argument(
        "--debug-hooks",
        action="store_true",
        help="Enable default lifecycle debug logging",
    )
    parser.add_argument("--version", action="store_true", help=f"Show {prog} version")
    return parser


def get_subparsers(
    parser: ArgumentParser,
    title: str = "Falyx Commands",
    description: str | None = "Available commands for the Falyx CLI.",
) -> _SubParsersAction:
    """
    Create and return a subparsers object for registering Falyx CLI subcommands.

    This function adds a `subparsers` block to the given root parser, enabling
    structured subcommands such as `run`, `run-all`, `preview`, etc.

    Args:
        parser (ArgumentParser): The root parser to attach the subparsers to.
        title (str): Title used in help output to group subcommands.
        description (str | None): Optional text describing the group of subcommands.

    Returns:
        _SubParsersAction: The subparsers object that can be used to add new CLI subcommands.

    Raises:
        TypeError: If `parser` is not an instance of `ArgumentParser`.

    Example:
        ```python
        >>> parser = get_root_parser()
        >>> subparsers = get_subparsers(parser, title="Available Commands")
        >>> subparsers.add_parser("run", help="Run a Falyx command")
        ```
    """
    if not isinstance(parser, ArgumentParser):
        raise TypeError("parser must be an instance of ArgumentParser")
    subparsers = parser.add_subparsers(
        title=title,
        description=description,
        dest="command",
    )
    return subparsers


def get_arg_parsers(
    prog: str | None = "falyx",
    usage: str | None = None,
    description: str | None = "Falyx CLI - Run structured async command workflows.",
    epilog: (
        str | None
    ) = "Tip: Use 'falyx run ?[COMMAND]' to preview any command from the CLI.",
    parents: Sequence[ArgumentParser] | None = None,
    prefix_chars: str = "-",
    fromfile_prefix_chars: str | None = None,
    argument_default: Any = None,
    conflict_handler: str = "error",
    add_help: bool = True,
    allow_abbrev: bool = True,
    exit_on_error: bool = True,
    commands: dict[str, Command] | None = None,
    root_parser: ArgumentParser | None = None,
    subparsers: _SubParsersAction | None = None,
) -> FalyxParsers:
    """
    Create and return the full suite of argument parsers used by the Falyx CLI.

    This function builds the root parser and all subcommand parsers used for structured
    CLI workflows in Falyx. It supports standard subcommands including `run`, `run-all`,
    `preview`, `list`, and `version`, and integrates with registered `Command` objects
    to populate dynamic help and usage documentation.

    Args:
        prog (str | None): Program name to display in help and usage messages.
        usage (str | None): Optional usage message to override the default.
        description (str | None): Description for the CLI root parser.
        epilog (str | None): Epilog message shown after the help text.
        parents (Sequence[ArgumentParser] | None): Optional parent parsers.
        prefix_chars (str): Characters that prefix optional arguments.
        fromfile_prefix_chars (str | None): Prefix character for reading args from file.
        argument_default (Any): Default value for arguments if not specified.
        conflict_handler (str): Strategy for resolving conflicting arguments.
        add_help (bool): Whether to add the `-h/--help` option to the root parser.
        allow_abbrev (bool): Whether to allow abbreviated long options.
        exit_on_error (bool): Whether the parser exits on error or raises.
        commands (dict[str, Command] | None): Optional dictionary of registered commands
            to populate help and subcommand descriptions dynamically.
        root_parser (ArgumentParser | None): Custom root parser to use instead of building one.
        subparsers (_SubParsersAction | None): Optional existing subparser object to extend.

    Returns:
        FalyxParsers: A structured container of all parsers, including `run`, `run-all`,
                      `preview`, `list`, `version`, and the root parser.

    Raises:
        TypeError: If `root_parser` is not an instance of ArgumentParser or
                   `subparsers` is not an instance of _SubParsersAction.

    Example:
        ```python
        >>> parsers = get_arg_parsers(commands=my_command_dict)
        >>> args = parsers.root.parse_args()
        ```

    Notes:
        - This function integrates dynamic command usage and descriptions if the
          `commands` argument is provided.
        - The `run` parser supports additional options for retry logic and confirmation
          prompts.
        - The `run-all` parser executes all commands matching a tag.
        - Use `falyx run ?[COMMAND]` from the CLI to preview a command.
    """
    if epilog is None:
        epilog = f"Tip: Use '{prog} run ?[COMMAND]' to preview any command from the CLI."
    if root_parser is None:
        parser = get_root_parser(
            prog=prog,
            usage=usage,
            description=description,
            epilog=epilog,
            parents=parents,
            prefix_chars=prefix_chars,
            fromfile_prefix_chars=fromfile_prefix_chars,
            argument_default=argument_default,
            conflict_handler=conflict_handler,
            add_help=add_help,
            allow_abbrev=allow_abbrev,
            exit_on_error=exit_on_error,
        )
    else:
        if not isinstance(root_parser, ArgumentParser):
            raise TypeError("root_parser must be an instance of ArgumentParser")
        parser = root_parser

    if subparsers is None:
        if prog == "falyx":
            subparsers = get_subparsers(
                parser,
                title="Falyx Commands",
                description="Available commands for the Falyx CLI.",
            )
        else:
            subparsers = get_subparsers(parser, title="subcommands", description=None)
    if not isinstance(subparsers, _SubParsersAction):
        raise TypeError("subparsers must be an instance of _SubParsersAction")

    run_description = ["Run a command by its key or alias.\n"]
    run_description.append("commands:")
    if isinstance(commands, dict):
        for command in commands.values():
            run_description.append(command.usage)
            command_description = command.help_text or command.description
            run_description.append(f"{' '*24}{command_description}")
    run_epilog = (
        f"Tip: Use '{prog} run ?[COMMAND]' to preview commands by their key or alias."
    )
    run_parser = subparsers.add_parser(
        "run",
        help="Run a specific command",
        description="\n".join(run_description),
        epilog=run_epilog,
        formatter_class=RawDescriptionHelpFormatter,
    )
    run_parser.add_argument(
        "name", help="Run a command by its key or alias", metavar="COMMAND"
    )
    run_parser.add_argument(
        "--summary",
        action="store_true",
        help="Print an execution summary after command completes",
    )
    run_parser.add_argument(
        "--retries", type=int, help="Number of retries on failure", default=0
    )
    run_parser.add_argument(
        "--retry-delay",
        type=float,
        help="Initial delay between retries in (seconds)",
        default=0,
    )
    run_parser.add_argument(
        "--retry-backoff", type=float, help="Backoff factor for retries", default=0
    )
    run_group = run_parser.add_mutually_exclusive_group(required=False)
    run_group.add_argument(
        "-c",
        "--confirm",
        dest="force_confirm",
        action="store_true",
        help="Force confirmation prompts",
    )
    run_group.add_argument(
        "-s",
        "--skip-confirm",
        dest="skip_confirm",
        action="store_true",
        help="Skip confirmation prompts",
    )

    run_parser.add_argument(
        "command_args",
        nargs=REMAINDER,
        help="Arguments to pass to the command (if applicable)",
        metavar="ARGS",
    )

    run_all_parser = subparsers.add_parser(
        "run-all", help="Run all commands with a given tag"
    )
    run_all_parser.add_argument("-t", "--tag", required=True, help="Tag to match")
    run_all_parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a summary after all tagged commands run",
    )
    run_all_parser.add_argument(
        "--retries", type=int, help="Number of retries on failure", default=0
    )
    run_all_parser.add_argument(
        "--retry-delay",
        type=float,
        help="Initial delay between retries in (seconds)",
        default=0,
    )
    run_all_parser.add_argument(
        "--retry-backoff", type=float, help="Backoff factor for retries", default=0
    )
    run_all_group = run_all_parser.add_mutually_exclusive_group(required=False)
    run_all_group.add_argument(
        "-c",
        "--confirm",
        dest="force_confirm",
        action="store_true",
        help="Force confirmation prompts",
    )
    run_all_group.add_argument(
        "-s",
        "--skip-confirm",
        dest="skip_confirm",
        action="store_true",
        help="Skip confirmation prompts",
    )

    preview_parser = subparsers.add_parser(
        "preview", help="Preview a command without running it"
    )
    preview_parser.add_argument("name", help="Key, alias, or description of the command")

    list_parser = subparsers.add_parser(
        "list", help="List all available commands with tags"
    )

    list_parser.add_argument(
        "-t", "--tag", help="Filter commands by tag (case-insensitive)", default=None
    )

    version_parser = subparsers.add_parser("version", help=f"Show {prog} version")

    return FalyxParsers(
        root=parser,
        subparsers=subparsers,
        run=run_parser,
        run_all=run_all_parser,
        preview=preview_parser,
        list=list_parser,
        version=version_parser,
    )
