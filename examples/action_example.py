import asyncio

from falyx import Action, ActionGroup, ChainedAction


# Actions can be defined as synchronous functions
# Falyx will automatically convert them to async functions
def hello() -> None:
    print("Hello, world!")


hello_action = Action(name="hello_action", action=hello)

# Actions can be run by themselves or as part of a command or pipeline
asyncio.run(hello_action())


# Actions are designed to be asynchronous first
async def goodbye() -> None:
    print("Goodbye!")


goodbye_action = Action(name="goodbye_action", action=goodbye)

asyncio.run(goodbye())

# Actions can be run in parallel
group = ActionGroup(name="greeting_group", actions=[hello_action, goodbye_action])
asyncio.run(group())

# Actions can be run in a chain
chain = ChainedAction(name="greeting_chain", actions=[hello_action, goodbye_action])
asyncio.run(chain())
