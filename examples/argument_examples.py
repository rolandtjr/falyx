import asyncio
from enum import Enum
from pathlib import Path

from falyx import Falyx
from falyx.action import Action
from falyx.parser.command_argument_parser import CommandArgumentParser


class Place(Enum):
    """Enum for different places."""

    NEW_YORK = "New York"
    SAN_FRANCISCO = "San Francisco"
    LONDON = "London"

    def __str__(self):
        return self.value


async def test_args(
    service: str,
    place: Place = Place.NEW_YORK,
    region: str = "us-east-1",
    path: Path | None = None,
    tag: str | None = None,
    verbose: bool | None = None,
    numbers: list[int] | None = None,
    just_a_bool: bool = False,
) -> str:
    if numbers is None:
        numbers = []
    if verbose:
        print(
            f"Deploying {service}:{tag}:{"|".join(str(number) for number in numbers)} to {region} at {place} from {path}..."
        )
    return f"{service}:{tag}:{"|".join(str(number) for number in numbers)} deployed to {region} at {place} from {path}."


async def test_path_arg(*paths: Path) -> str:
    return f"Path argument received: {'|'.join(str(path) for path in paths)}"


async def test_positional_numbers(*numbers: int) -> str:
    return f"Positional numbers received: {', '.join(str(num) for num in numbers)}"


def default_config(parser: CommandArgumentParser) -> None:
    """Default argument configuration for the command."""
    parser.add_argument(
        "service",
        type=str,
        choices=["web", "database", "cache"],
        help="Service name to deploy.",
    )
    parser.add_argument(
        "place",
        type=Place,
        choices=list(Place),
        default=Place.NEW_YORK,
        help="Place where the service will be deployed.",
    )
    parser.add_argument(
        "--region",
        type=str,
        default="us-east-1",
        help="Deployment region.",
        choices=["us-east-1", "us-west-2", "eu-west-1"],
    )
    parser.add_argument(
        "-p",
        "--path",
        type=Path,
        help="Path to the configuration file.",
    )
    parser.add_argument(
        "--verbose",
        action="store_bool_optional",
        help="Enable verbose output.",
    )
    parser.add_argument(
        "-t",
        "--tag",
        type=str,
        help="Optional tag for the deployment.",
        suggestions=["latest", "stable", "beta"],
    )
    parser.add_argument(
        "--numbers",
        type=int,
        nargs="*",
        default=[1, 2, 3],
        help="Optional number argument.",
    )
    parser.add_argument(
        "-j",
        "--just-a-bool",
        action="store_true",
        help="Just a boolean flag.",
    )
    parser.add_tldr_examples(
        [
            ("web", "Deploy 'web' to the default location (New York)"),
            ("cache London --tag beta", "Deploy 'cache' to London with tag"),
            ("database --region us-west-2 --verbose", "Verbose deploy to west region"),
        ]
    )


def path_config(parser: CommandArgumentParser) -> None:
    """Argument configuration for path testing command."""
    parser.add_argument(
        "paths",
        type=Path,
        nargs="*",
        help="One or more file or directory paths.",
    )
    parser.add_tldr_examples(
        [
            ("/path/to/file.txt", "Single file path"),
            ("/path/to/dir1 /path/to/dir2", "Multiple directory paths"),
            ("/path/with spaces/file.txt", "Path with spaces"),
        ]
    )


def numbers_config(parser: CommandArgumentParser) -> None:
    """Argument configuration for positional numbers testing command."""
    parser.add_argument(
        "numbers",
        type=int,
        nargs="*",
        help="One or more integers.",
    )
    parser.add_tldr_examples(
        [
            ("1 2 3", "Three numbers"),
            ("42", "Single number"),
            ("", "No numbers"),
        ]
    )


flx = Falyx(
    "Argument Examples",
    program="argument_examples.py",
    hide_menu_table=True,
    show_placeholder_menu=True,
    enable_prompt_history=True,
)

flx.add_command(
    key="T",
    aliases=["test"],
    description="Test Command",
    help_text="A command to test argument parsing.",
    action=Action(
        name="test_args",
        action=test_args,
    ),
    style="bold #B3EBF2",
    argument_config=default_config,
)

flx.add_command(
    key="P",
    aliases=["path"],
    description="Path Command",
    help_text="A command to test path argument parsing.",
    action=Action(
        name="test_path_arg",
        action=test_path_arg,
    ),
    style="bold #F2B3EB",
    argument_config=path_config,
)

flx.add_command(
    key="N",
    aliases=["numbers"],
    description="Numbers Command",
    help_text="A command to test positional numbers argument parsing.",
    action=Action(
        name="test_positional_numbers",
        action=test_positional_numbers,
    ),
    style="bold #F2F2B3",
    argument_config=numbers_config,
)

asyncio.run(flx.run())
