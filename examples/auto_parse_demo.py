import asyncio

from falyx import Falyx
from falyx.action import Action, ChainedAction
from falyx.utils import setup_logging

setup_logging()


async def deploy(service: str, region: str = "us-east-1", verbose: bool = False) -> str:
    if verbose:
        print(f"Deploying {service} to {region}...")
    await asyncio.sleep(2)
    if verbose:
        print(f"{service} deployed successfully!")
    return f"{service} deployed to {region}"


flx = Falyx("Deployment CLI")

flx.add_command(
    key="D",
    aliases=["deploy"],
    description="Deploy",
    help_text="Deploy a service to a specified region.",
    action=Action(
        name="deploy_service",
        action=deploy,
    ),
    arg_metadata={
        "service": "Service name",
        "region": {"help": "Deployment region", "choices": ["us-east-1", "us-west-2"]},
        "verbose": {"help": "Enable verbose mode"},
    },
    tags=["deployment", "service"],
)

deploy_chain = ChainedAction(
    name="DeployChain",
    actions=[
        Action(name="deploy_service", action=deploy),
        Action(
            name="notify",
            action=lambda last_result: print(f"Notification: {last_result}"),
        ),
    ],
    auto_inject=True,
)

flx.add_command(
    key="N",
    aliases=["notify"],
    description="Deploy and Notify",
    help_text="Deploy a service and notify.",
    action=deploy_chain,
    tags=["deployment", "service", "notification"],
)

asyncio.run(flx.run())
