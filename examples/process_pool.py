from rich.console import Console

from falyx import Falyx
from falyx.action import ProcessPoolAction
from falyx.action.process_pool_action import ProcessTask
from falyx.execution_registry import ExecutionRegistry as er
from falyx.themes import NordColors as nc

console = Console()
falyx = Falyx(title="🚀 Process Pool Demo")


def generate_primes(start: int = 2, end: int = 100_000) -> list[int]:
    primes: list[int] = []
    console.print(f"Generating primes from {start} to {end}...", style=nc.YELLOW)
    for num in range(start, end):
        if all(num % p != 0 for p in primes):
            primes.append(num)
    console.print(
        f"Generated {len(primes)} primes from {start} to {end}.", style=nc.GREEN
    )
    return primes


actions = [ProcessTask(task=generate_primes)]

# Will not block the event loop
heavy_action = ProcessPoolAction(
    name="Prime Generator",
    actions=actions,
)

falyx.add_command("R", "Generate Primes", heavy_action)


if __name__ == "__main__":
    import asyncio

    # Run the menu
    asyncio.run(falyx.run())
