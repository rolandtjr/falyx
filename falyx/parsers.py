"""parsers.py
This module contains the argument parsers used for the Falyx CLI.
"""
from dataclasses import asdict, dataclass
from argparse import ArgumentParser


@dataclass
class FalyxParsers:
    """Defines the argument parsers for the Falyx CLI."""
    root: ArgumentParser
    run: ArgumentParser
    run_all: ArgumentParser
    preview: ArgumentParser
    list: ArgumentParser
    version: ArgumentParser

    def as_dict(self) -> dict[str, ArgumentParser]:
        """Convert the FalyxParsers instance to a dictionary."""
        return asdict(self)

    def get_parser(self, name: str) -> ArgumentParser | None:
        """Get the parser by name."""
        return self.as_dict().get(name)


def get_arg_parsers() -> FalyxParsers:
    """Returns the argument parser for the CLI."""
    parser = ArgumentParser(prog="falyx", description="Falyx CLI - Run structured async command workflows.")
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
