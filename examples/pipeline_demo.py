import asyncio
import random
import time

from falyx import Falyx
from falyx.action import Action, ActionGroup, ChainedAction, ProcessAction
from falyx.retry import RetryHandler, RetryPolicy


# Step 1: Fast I/O-bound setup (standard Action)
async def checkout_code():
    print("📥 Checking out code...")
    await asyncio.sleep(0.5)


# Step 2: CPU-bound task (ProcessAction)
def run_static_analysis():
    print("🧠 Running static analysis (CPU-bound)...")
    total = 0
    for i in range(10_000_000):
        total += i % 3
    time.sleep(5)
    return total


# Step 3: Simulated flaky test with retry
async def flaky_tests():
    await asyncio.sleep(0.3)
    if random.random() < 0.3:
        raise RuntimeError("❌ Random test failure!")
    print("🧪 Tests passed.")
    return "ok"


# Step 4: Multiple deploy targets (parallel ActionGroup)
async def deploy_to(target: str):
    print(f"🚀 Deploying to {target}...")
    await asyncio.sleep(random.randint(2, 6))
    return f"{target} complete"


def build_pipeline():
    retry_handler = RetryHandler(RetryPolicy(max_retries=3, delay=0.5))

    # Base actions
    checkout = Action("Checkout", checkout_code)
    analysis = ProcessAction(
        "Static Analysis",
        run_static_analysis,
        spinner=True,
        spinner_message="Analyzing code...",
    )
    tests = Action("Run Tests", flaky_tests)
    tests.hooks.register("on_error", retry_handler.retry_on_error)

    # Parallel deploys
    deploy_group = ActionGroup(
        "Deploy to All",
        [
            Action(
                "Deploy US",
                deploy_to,
                args=("us-west",),
                spinner=True,
                spinner_message="Deploying US...",
            ),
            Action(
                "Deploy EU",
                deploy_to,
                args=("eu-central",),
                spinner=True,
                spinner_message="Deploying EU...",
            ),
            Action(
                "Deploy Asia",
                deploy_to,
                args=("asia-east",),
                spinner=True,
                spinner_message="Deploying Asia...",
            ),
        ],
    )

    # Full pipeline
    return ChainedAction("CI/CD Pipeline", [checkout, analysis, tests, deploy_group])


pipeline = build_pipeline()


# Run the pipeline
async def main():

    flx = Falyx()
    flx.add_command(
        "A",
        "Action Thing",
        pipeline,
        spinner=True,
        spinner_type="line",
        spinner_message="Running pipeline...",
    )

    await flx.run()


if __name__ == "__main__":
    asyncio.run(main())
