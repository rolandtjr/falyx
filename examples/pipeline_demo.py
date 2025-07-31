import asyncio
import random
import time

from falyx import Falyx
from falyx.action import Action, ActionGroup, ChainedAction, ProcessAction
from falyx.console import console


# Step 1: Fast I/O-bound setup (standard Action)
async def checkout_code():
    console.print("🔄 Checking out code...")
    await asyncio.sleep(0.5)
    console.print("📦 Code checked out successfully.")


# Step 2: CPU-bound task (ProcessAction)
def run_static_analysis():
    total = 0
    for i in range(10_000_000):
        total += i % 3
    time.sleep(2)
    return total


# Step 3: Simulated flaky test with retry
async def flaky_tests():
    console.print("🧪 Running tests...")
    await asyncio.sleep(0.3)
    if random.random() < 0.3:
        raise RuntimeError("❌ Random test failure!")
    console.print("🧪 Tests passed.")
    return "ok"


# Step 4: Multiple deploy targets (parallel ActionGroup)
async def deploy_to(target: str):
    console.print(f"🚀 Deploying to {target}...")
    await asyncio.sleep(random.randint(2, 6))
    console.print(f"✅ Deployment to {target} complete.")
    return f"{target} complete"


def build_pipeline():
    # Base actions
    checkout = Action("Checkout", checkout_code)
    analysis = ProcessAction(
        "Static Analysis",
        run_static_analysis,
        spinner=True,
        spinner_message="Analyzing code...",
    )
    analysis.hooks.register(
        "before", lambda ctx: console.print("🧠 Running static analysis (CPU-bound)...")
    )
    analysis.hooks.register("after", lambda ctx: console.print("🧠 Analysis complete!"))
    tests = Action(
        "Run Tests",
        flaky_tests,
        retry=True,
        spinner=True,
        spinner_message="Running tests...",
    )

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

    flx = Falyx(
        hide_menu_table=True, program="pipeline_demo.py", show_placeholder_menu=True
    )
    flx.add_command(
        "P",
        "Run Pipeline",
        pipeline,
        spinner=True,
        spinner_type="line",
        spinner_message="Running pipeline...",
        tags=["pipeline", "demo"],
        help_text="Run the full CI/CD pipeline demo.",
    )

    await flx.run()


if __name__ == "__main__":
    asyncio.run(main())
