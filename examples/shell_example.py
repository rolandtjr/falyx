#!/usr/bin/env python
import asyncio

from falyx import Action, ChainedAction, Falyx
from falyx.action import ShellAction
from falyx.hooks import ResultReporter
from falyx.utils import setup_logging

# Setup logging
setup_logging()


fx = Falyx("🚀 Falyx Demo")

e = ShellAction("Shell", "echo Hello, {}!")

fx.add_command(
    key="R",
    description="Echo a message",
    action=e,
)

s = ShellAction("Ping", "ping -c 1 {}")

fx.add_command(
    key="P",
    description="Ping a host",
    action=s,
)


async def a1(last_result):
    return f"Hello, {last_result}"


async def a2(last_result):
    return f"World! {last_result}"


reporter = ResultReporter()

a1 = Action("a1", a1, inject_last_result=True)
a1.hooks.register(
    "on_success",
    reporter.report,
)
a2 = Action("a2", a2, inject_last_result=True)
a2.hooks.register(
    "on_success",
    reporter.report,
)


async def normal():
    print("Normal")
    return "Normal"


async def annotate(last_result):
    return f"Annotated: {last_result}"


async def whisper(last_result):
    return last_result.lower()


c1 = ChainedAction(
    name="ShellDemo",
    actions=[
        # host,
        ShellAction("Ping", "ping -c 1 {}"),
        Action("Annotate", annotate),
        Action("Whisper", whisper),
    ],
    auto_inject=True,
)

fx.add_command(
    key="C",
    description="Run a chain of actions",
    action=c1,
)


async def main():
    await fx.run()


asyncio.run(main())
