import asyncio

from falyx import Action, ActionGroup, ChainedAction
from falyx import ExecutionRegistry as er
from falyx import ProcessAction
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
    return total


# Step 3: Simulated flaky test with retry
async def flaky_tests():
    import random

    await asyncio.sleep(0.3)
    if random.random() < 0.3:
        raise RuntimeError("❌ Random test failure!")
    print("🧪 Tests passed.")
    return "ok"


# Step 4: Multiple deploy targets (parallel ActionGroup)
async def deploy_to(target: str):
    print(f"🚀 Deploying to {target}...")
    await asyncio.sleep(0.2)
    return f"{target} complete"


def build_pipeline():
    retry_handler = RetryHandler(RetryPolicy(max_retries=3, delay=0.5))

    # Base actions
    checkout = Action("Checkout", checkout_code)
    analysis = ProcessAction("Static Analysis", run_static_analysis)
    tests = Action("Run Tests", flaky_tests)
    tests.hooks.register("on_error", retry_handler.retry_on_error)

    # Parallel deploys
    deploy_group = ActionGroup(
        "Deploy to All",
        [
            Action("Deploy US", deploy_to, args=("us-west",)),
            Action("Deploy EU", deploy_to, args=("eu-central",)),
            Action("Deploy Asia", deploy_to, args=("asia-east",)),
        ],
    )

    # Full pipeline
    return ChainedAction("CI/CD Pipeline", [checkout, analysis, tests, deploy_group])


pipeline = build_pipeline()


# Run the pipeline
async def main():
    pipeline = build_pipeline()
    await pipeline()
    er.summary()
    await pipeline.preview()


if __name__ == "__main__":
    asyncio.run(main())
