import asyncio

from falyx import Falyx
from falyx.action import SelectFileAction
from falyx.action.action_types import FileType

sf = SelectFileAction(
    name="select_file",
    suffix_filter=".yaml",
    title="Select a YAML file",
    prompt_message="Choose 2 > ",
    return_type=FileType.TEXT,
    columns=3,
    number_selections=2,
)

flx = Falyx(
    title="File Selection Example",
    description="This example demonstrates how to select files using Falyx.",
    version="1.0.0",
    program="file_select.py",
    hide_menu_table=True,
    show_placeholder_menu=True,
)

flx.add_command(
    key="S",
    description="Select a file",
    action=sf,
    help_text="Select a file from the current directory",
)

if __name__ == "__main__":
    asyncio.run(flx.run())
