"""config_loading.py"""

from falyx.config import loader

flx = loader("falyx.yaml")

if __name__ == "__main__":
    import asyncio

    asyncio.run(flx.run())
