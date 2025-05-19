import asyncio

from falyx import Action, Falyx


async def deploy(service: str, region: str = "us-east-1", verbose: bool = False):
    if verbose:
        print(f"Deploying {service} to {region}...")
    await asyncio.sleep(2)
    if verbose:
        print(f"{service} deployed successfully!")


flx = Falyx("Deployment CLI")

flx.add_command(
    key="D",
    aliases=["deploy"],
    description="Deploy a service to a specified region.",
    action=Action(
        name="deploy_service",
        action=deploy,
    ),
    auto_args=True,
    arg_metadata={
        "service": "Service name",
        "region": {"help": "Deployment region", "choices": ["us-east-1", "us-west-2"]},
        "verbose": {"help": "Enable verbose mode"},
    },
)

asyncio.run(flx.run())
