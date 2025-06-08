import asyncio
from uuid import UUID, uuid4

from falyx import Falyx
from falyx.parser import CommandArgumentParser

flx = Falyx("Test Type Validation")


def uuid_val(value: str) -> str:
    """Custom validator to ensure a string is a valid UUID."""
    UUID(value)
    return value


async def print_uuid(uuid: str) -> str:
    """Prints the UUID if valid."""
    print(f"Valid UUID: {uuid}")
    return uuid


flx.add_command(
    "U",
    "Print a valid UUID (arguemnts)",
    print_uuid,
    arguments=[
        {
            "flags": ["uuid"],
            "type": uuid_val,
            "help": "A valid UUID string",
        }
    ],
)


def uuid_parser(parser: CommandArgumentParser) -> None:
    """Custom parser to ensure the UUID argument is valid."""
    parser.add_argument(
        "uuid",
        type=uuid_val,
        help="A valid UUID string",
    )


flx.add_command(
    "I",
    "Print a valid UUID (argument_config)",
    print_uuid,
    argument_config=uuid_parser,
)

flx.add_command(
    "D",
    "Print a valid UUID (arg_metadata)",
    print_uuid,
    arg_metadata={
        "uuid": {
            "type": uuid_val,
            "help": "A valid UUID string",
        }
    },
)


def custom_parser(arguments: list[str]) -> tuple[tuple, dict]:
    """Custom parser to ensure the UUID argument is valid."""
    if len(arguments) != 1:
        raise ValueError("Exactly one argument is required")
    uuid_val(arguments[0])
    return (arguments[0],), {}


flx.add_command(
    "C",
    "Print a valid UUID (custom_parser)",
    print_uuid,
    custom_parser=custom_parser,
)


async def generate_uuid() -> str:
    """Generates a new UUID."""
    new_uuid = uuid4()
    print(f"Generated UUID: {new_uuid}")
    return new_uuid


flx.add_command(
    "G",
    "Generate a new UUID",
    lambda: print(uuid4()),
)


async def main() -> None:
    await flx.run()


if __name__ == "__main__":
    asyncio.run(main())
