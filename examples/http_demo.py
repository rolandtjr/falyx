import asyncio

from rich.console import Console

from falyx import ActionGroup, Falyx
from falyx.action import HTTPAction
from falyx.hook_manager import HookType
from falyx.hooks import ResultReporter

console = Console()


action_group = ActionGroup(
    "HTTP Group",
    actions=[
        HTTPAction(
            name="Get Example",
            method="GET",
            url="https://jsonplaceholder.typicode.com/posts/1",
            headers={"Accept": "application/json"},
            retry=True,
        ),
        HTTPAction(
            name="Post Example",
            method="POST",
            url="https://jsonplaceholder.typicode.com/posts",
            headers={"Content-Type": "application/json"},
            json={"title": "foo", "body": "bar", "userId": 1},
            retry=True,
        ),
        HTTPAction(
            name="Put Example",
            method="PUT",
            url="https://jsonplaceholder.typicode.com/posts/1",
            headers={"Content-Type": "application/json"},
            json={"id": 1, "title": "foo", "body": "bar", "userId": 1},
            retry=True,
        ),
        HTTPAction(
            name="Delete Example",
            method="DELETE",
            url="https://jsonplaceholder.typicode.com/posts/1",
            headers={"Content-Type": "application/json"},
            retry=True,
        ),
    ],
)

reporter = ResultReporter()

action_group.hooks.register(
    HookType.ON_SUCCESS,
    reporter.report,
)

flx = Falyx("HTTP Demo")

flx.add_command(
    key="G",
    description="Run HTTP Action Group",
    action=action_group,
    spinner=True,
)


if __name__ == "__main__":
    asyncio.run(flx.run())
