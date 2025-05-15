import asyncio

from prompt_toolkit.validation import Validator

from falyx.action import Action, ChainedAction, UserInputAction


def validate_alpha() -> Validator:
    def validate(text: str) -> bool:
        return text.isalpha()

    return Validator.from_callable(
        validate,
        error_message="Please enter only alphabetic characters.",
        move_cursor_to_end=True,
    )


chain = ChainedAction(
    name="Demo Chain",
    actions=[
        "Name",
        UserInputAction(
            name="User Input",
            prompt_text="Enter your {last_result}: ",
            validator=validate_alpha(),
        ),
        Action(
            name="Display Name",
            action=lambda last_result: print(f"Hello, {last_result}!"),
        ),
    ],
    auto_inject=True,
)

if __name__ == "__main__":
    asyncio.run(chain.preview())
    asyncio.run(chain())
