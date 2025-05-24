import asyncio

from falyx.action import SelectionAction
from falyx.selection import SelectionOption
from falyx.signals import CancelSignal

selections = {
    "1": SelectionOption(
        description="Production", value="3bc2616e-3696-11f0-a139-089204eb86ac"
    ),
    "2": SelectionOption(
        description="Staging", value="42f2cd84-3696-11f0-a139-089204eb86ac"
    ),
}


select = SelectionAction(
    name="Select Deployment",
    selections=selections,
    title="Select a Deployment",
    columns=2,
    prompt_message="> ",
    return_type="value",
    show_table=True,
)

try:
    print(asyncio.run(select()))
except CancelSignal:
    print("Selection was cancelled.")
