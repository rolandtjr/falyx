import asyncio
from enum import Enum

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
    tag: str | None = None,
    verbose: bool | None = None,
    number: int | None = None,
) -> str:
    if verbose:
        print(f"Deploying {service}:{tag}:{number} to {region} at {place}...")
    return f"{service}:{tag}:{number} deployed to {region} at {place}"


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
        "--verbose",
        action="store_bool_optional",
        help="Enable verbose output.",
    )
    parser.add_argument(
        "--tag",
        type=str,
        help="Optional tag for the deployment.",
        suggestions=["latest", "stable", "beta"],
    )
    parser.add_argument(
        "--number",
        type=int,
        help="Optional number argument.",
    )


flx = Falyx("Argument Examples")

flx.add_command(
    key="T",
    aliases=["test"],
    description="Test Command",
    help_text="A command to test argument parsing.",
    action=Action(
        name="test_args",
        action=test_args,
    ),
    argument_config=default_config,
)

asyncio.run(flx.run())
