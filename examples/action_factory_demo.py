import asyncio

from falyx import Falyx
from falyx.action import ActionFactory, ChainedAction, HTTPAction, SelectionAction

# Selection of a post ID to fetch (just an example set)
post_selector = SelectionAction(
    name="Pick Post ID",
    selections=["15", "25", "35", "45", "55"],
    title="Choose a Post ID to submit",
    prompt_message="Post ID > ",
    show_table=True,
)


# Factory that builds and executes the actual HTTP POST request
async def build_post_action(post_id) -> HTTPAction:
    print(f"Building HTTPAction for Post ID: {post_id}")
    return HTTPAction(
        name=f"POST to /posts (id={post_id})",
        method="POST",
        url="https://jsonplaceholder.typicode.com/posts",
        json={"title": "foo", "body": "bar", "userId": int(post_id)},
    )


post_factory = ActionFactory(
    name="Build HTTPAction from Post ID",
    factory=build_post_action,
    inject_last_result=True,
    inject_into="post_id",
    preview_kwargs={"post_id": "100"},
)

# Wrap in a ChainedAction
chain = ChainedAction(
    name="Submit Post Flow",
    actions=[post_selector, post_factory],
    auto_inject=True,
)

flx = Falyx()
flx.add_command(
    key="S",
    description="Submit a Post",
    action=chain,
)
asyncio.run(flx.run())
