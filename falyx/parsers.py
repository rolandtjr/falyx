"""parsers.py
This module contains the argument parsers used for the Falyx CLI.
"""
from argparse import ArgumentParser, HelpFormatter, Namespace
from dataclasses import asdict, dataclass
from typing import Any, Sequence


@dataclass
class FalyxParsers:
    """Defines the argument parsers for the Falyx CLI."""
    root: ArgumentParser
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


def get_arg_parsers(
        prog: str |None = "falyx",
        usage: str | None = None,
        description: str | None = "Falyx CLI - Run structured async command workflows.",
        epilog: str | None = None,
        parents: Sequence[ArgumentParser] = [],
        formatter_class: HelpFormatter = HelpFormatter,
        prefix_chars: str = "-",
        fromfile_prefix_chars: str | None = None,
        argument_default: Any = None,
        conflict_handler: str = "error",
        add_help: bool = True,
        allow_abbrev: bool = True,
        exit_on_error: bool = True,
    ) -> FalyxParsers:
    """Returns the argument parser for the CLI."""
    parser = ArgumentParser(
        prog=prog,
        usage=usage,
        description=description,
        epilog=epilog,
        parents=parents,
        formatter_class=formatter_class,
        prefix_chars=prefix_chars,
        fromfile_prefix_chars=fromfile_prefix_chars,
        argument_default=argument_default,
        conflict_handler=conflict_handler,
        add_help=add_help,
        allow_abbrev=allow_abbrev,
        exit_on_error=exit_on_error,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging for Falyx.")
    parser.add_argument("--debug-hooks", action="store_true", help="Enable default lifecycle debug logging")
    parser.add_argument("--version", action="store_true", help="Show Falyx version")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a specific command")
    run_parser.add_argument("name", help="Key, alias, or description of the command")
    run_parser.add_argument("--retries", type=int, help="Number of retries on failure", default=0)
    run_parser.add_argument("--retry-delay", type=float, help="Initial delay between retries in (seconds)", default=0)
    run_parser.add_argument("--retry-backoff", type=float, help="Backoff factor for retries", default=0)
    run_group = run_parser.add_mutually_exclusive_group(required=False)
    run_group.add_argument("-c", "--confirm", dest="force_confirm", action="store_true", help="Force confirmation prompts")
    run_group.add_argument("-s", "--skip-confirm", dest="skip_confirm", action="store_true", help="Skip confirmation prompts")

    run_all_parser = subparsers.add_parser("run-all", help="Run all commands with a given tag")
    run_all_parser.add_argument("-t", "--tag", required=True, help="Tag to match")
    run_all_parser.add_argument("--retries", type=int, help="Number of retries on failure", default=0)
    run_all_parser.add_argument("--retry-delay", type=float, help="Initial delay between retries in (seconds)", default=0)
    run_all_parser.add_argument("--retry-backoff", type=float, help="Backoff factor for retries", default=0)
    run_all_group = run_all_parser.add_mutually_exclusive_group(required=False)
    run_all_group.add_argument("-c", "--confirm", dest="force_confirm", action="store_true", help="Force confirmation prompts")
    run_all_group.add_argument("-s", "--skip-confirm", dest="skip_confirm", action="store_true", help="Skip confirmation prompts")

    preview_parser = subparsers.add_parser("preview", help="Preview a command without running it")
    preview_parser.add_argument("name", help="Key, alias, or description of the command")

    list_parser = subparsers.add_parser("list", help="List all available commands with tags")

    version_parser = subparsers.add_parser("version", help="Show the Falyx version")

    return FalyxParsers(
        root=parser,
        run=run_parser,
        run_all=run_all_parser,
        preview=preview_parser,
        list=list_parser,
        version=version_parser,
    )
