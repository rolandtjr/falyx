# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""parsers.py
This module contains the argument parsers used for the Falyx CLI.
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
    """Create and return a subparsers action for the given parser."""
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
    """Returns the argument parser for the CLI."""
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
