import asyncio

from falyx import Falyx
from falyx.action import Action


async def main():
    state = {"count": 0}

    async def flaky():
        if not state["count"]:
            state["count"] += 1
            print("Flaky step failed, retrying...")
            raise RuntimeError("Random failure!")
        return "ok"

    # Add a command that raises an exception
    falyx.add_command(
        key="E",
        description="Error Command",
        action=Action("flaky", flaky),
        retry=True,
    )

    result = await falyx.run_key("E")
    print(result)
    assert result == "ok"


if __name__ == "__main__":
    falyx = Falyx("Headless Recovery Test")
    asyncio.run(main())
