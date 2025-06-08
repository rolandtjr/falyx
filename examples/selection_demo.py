import asyncio
from uuid import uuid4

from falyx import Falyx
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

list_selections = [uuid4() for _ in range(10)]

list_select = SelectionAction(
    name="Select Deployments",
    selections=list_selections,
    title="Select Deployments",
    columns=3,
    prompt_message="Select 3 Deployments > ",
    return_type="value",
    show_table=True,
    number_selections=3,
)


flx = Falyx()

flx.add_command(
    key="S",
    description="Select a deployment",
    action=select,
    help_text="Select a deployment from the list",
)
flx.add_command(
    key="L",
    description="Select deployments",
    action=list_select,
    help_text="Select multiple deployments from the list",
)

if __name__ == "__main__":

    try:
        print(asyncio.run(select()))
    except CancelSignal:
        print("Selection was cancelled.")

    try:
        print(asyncio.run(list_select()))
    except CancelSignal:
        print("Selection was cancelled.")

    asyncio.run(flx.run())
