import asyncio

from falyx import Falyx
from falyx.action import Action, ActionGroup


# Define a shared async function
async def say_hello(name: str, excited: bool = False):
    if excited:
        print(f"Hello, {name}!!!")
    else:
        print(f"Hello, {name}.")


# Wrap the same callable in multiple Actions
action1 = Action("say_hello_1", action=say_hello)
action2 = Action("say_hello_2", action=say_hello)
action3 = Action("say_hello_3", action=say_hello)

# Combine into an ActionGroup
group = ActionGroup(name="greet_group", actions=[action1, action2, action3])

flx = Falyx("Test Group")
flx.add_command(
    key="G",
    description="Greet someone with multiple variations.",
    aliases=["greet", "hello"],
    action=group,
    arg_metadata={
        "name": {
            "help": "The name of the person to greet.",
        },
        "excited": {
            "help": "Whether to greet excitedly.",
        },
    },
)
asyncio.run(flx.run())
