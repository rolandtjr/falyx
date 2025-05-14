import asyncio

from falyx.action import HTTPAction

http_action = HTTPAction(
    name="Get Example",
    method="GET",
    url="https://jsonplaceholder.typicode.com/posts/1",
    headers={"Accept": "application/json"},
    retry=True,
)

if __name__ == "__main__":
    asyncio.run(http_action())
