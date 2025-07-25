import asyncio
from typing import Any

from pydantic import BaseModel

from falyx import Falyx
from falyx.action import (
    Action,
    ActionFactory,
    ChainedAction,
    ConfirmAction,
    SaveFileAction,
)
from falyx.parser import CommandArgumentParser


class Dog(BaseModel):
    name: str
    age: int
    breed: str


async def get_dogs(*dog_names: str) -> list[Dog]:
    """Simulate fetching dog data."""
    await asyncio.sleep(0.1)  # Simulate network delay
    dogs = [
        Dog(name="Buddy", age=3, breed="Golden Retriever"),
        Dog(name="Max", age=5, breed="Beagle"),
        Dog(name="Bella", age=2, breed="Bulldog"),
        Dog(name="Charlie", age=4, breed="Poodle"),
        Dog(name="Lucy", age=1, breed="Labrador"),
        Dog(name="Spot", age=6, breed="German Shepherd"),
    ]
    dogs = [
        dog for dog in dogs if dog.name.upper() in (name.upper() for name in dog_names)
    ]
    if not dogs:
        raise ValueError(f"No dogs found with the names: {', '.join(dog_names)}")
    return dogs


async def build_json_updates(dogs: list[Dog]) -> list[dict[str, Any]]:
    """Build JSON updates for the dogs."""
    print(f"Building JSON updates for {','.join(dog.name for dog in dogs)}")
    return [dog.model_dump(mode="json") for dog in dogs]


async def save_dogs(dogs) -> None:
    if not dogs:
        print("No dogs processed.")
        return
    for result in dogs:
        print(f"Saving {Dog(**result)} to file.")
        await SaveFileAction(
            name="Save Dog Data",
            file_path=f"dogs/{result['name']}.json",
            data=result,
            file_type="json",
        )()


async def build_chain(dogs: list[Dog]) -> ChainedAction:
    return ChainedAction(
        name="test_chain",
        actions=[
            Action(
                name="build_json_updates",
                action=build_json_updates,
                kwargs={"dogs": dogs},
            ),
            ConfirmAction(
                name="test_confirm",
                prompt_message="Do you want to process the dogs?",
                confirm_type="yes_no_cancel",
                return_last_result=True,
                inject_into="dogs",
            ),
            Action(
                name="save_dogs",
                action=save_dogs,
                inject_into="dogs",
            ),
        ],
        auto_inject=True,
    )


factory = ActionFactory(
    name="Dog Post Factory",
    factory=build_chain,
    preview_kwargs={"dogs": ["Buddy", "Max"]},
)


def dog_config(parser: CommandArgumentParser) -> None:
    parser.add_argument(
        "dogs",
        nargs="+",
        action="action",
        resolver=Action("Get Dogs", get_dogs),
        lazy_resolver=False,
        help="List of dogs to process.",
    )


async def main():
    flx = Falyx("Save Dogs Example")

    flx.add_command(
        key="D",
        description="Save Dog Data",
        action=factory,
        aliases=["save_dogs"],
        argument_config=dog_config,
    )

    await flx.run()


if __name__ == "__main__":
    asyncio.run(main())
