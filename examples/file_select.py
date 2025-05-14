import asyncio

from falyx import Falyx
from falyx.action import SelectFileAction
from falyx.action.types import FileReturnType

sf = SelectFileAction(
    name="select_file",
    suffix_filter=".py",
    title="Select a YAML file",
    prompt_message="Choose > ",
    return_type=FileReturnType.TEXT,
    columns=3,
)

flx = Falyx()

flx.add_command(
    key="S",
    description="Select a file",
    action=sf,
    help_text="Select a file from the current directory",
)

if __name__ == "__main__":
    asyncio.run(flx.run())
