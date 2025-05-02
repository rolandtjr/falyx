from rich.console import Console

from falyx import Falyx, ProcessAction
from falyx.themes.colors import NordColors as nc

console = Console()
falyx = Falyx(title="🚀 Process Pool Demo")


def generate_primes(n):
    primes = []
    for num in range(2, n):
        if all(num % p != 0 for p in primes):
            primes.append(num)
    console.print(f"Generated {len(primes)} primes up to {n}.", style=nc.GREEN)
    return primes


# Will not block the event loop
heavy_action = ProcessAction("Prime Generator", generate_primes, args=(100_000,))

falyx.add_command("R", "Generate Primes", heavy_action, spinner=True)


if __name__ == "__main__":
    import asyncio

    # Run the menu
    asyncio.run(falyx.run())
