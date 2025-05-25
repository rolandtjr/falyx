import asyncio
import random

from falyx import Falyx
from falyx.action import Action, ChainedAction
from falyx.utils import setup_logging

setup_logging()


# A flaky async step that fails randomly
async def flaky_step():
    await asyncio.sleep(0.2)
    if random.random() < 0.5:
        raise RuntimeError("Random failure!")
    return "ok"


step1 = Action(name="step_1", action=flaky_step, retry=True)
step2 = Action(name="step_2", action=flaky_step, retry=True)

# Chain the actions
chain = ChainedAction(name="my_pipeline", actions=[step1, step2])

# Create the CLI menu
falyx = Falyx("🚀 Falyx Demo")
falyx.add_command(
    key="R",
    description="Run My Pipeline",
    action=chain,
    logging_hooks=True,
    preview_before_confirm=True,
    confirm=True,
)

# Create a submenu
submenu = Falyx("Submenu")
submenu.add_command(
    key="T",
    description="Test",
    action=lambda: "test",
    logging_hooks=True,
    preview_before_confirm=True,
    confirm=True,
)
falyx.add_submenu(
    key="S",
    description="Submenu",
    submenu=submenu,
)

if __name__ == "__main__":
    asyncio.run(falyx.run())
