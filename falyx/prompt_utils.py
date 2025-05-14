# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""prompt_utils.py"""
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import (
    AnyFormattedText,
    FormattedText,
    merge_formatted_text,
)

from falyx.options_manager import OptionsManager
from falyx.themes import OneColors
from falyx.validators import yes_no_validator


def should_prompt_user(
    *,
    confirm: bool,
    options: OptionsManager,
    namespace: str = "cli_args",
):
    """
    Determine whether to prompt the user for confirmation based on command
    and global options.
    """
    never_prompt = options.get("never_prompt", False, namespace)
    force_confirm = options.get("force_confirm", False, namespace)
    skip_confirm = options.get("skip_confirm", False, namespace)

    if never_prompt or skip_confirm:
        return False

    return confirm or force_confirm


async def confirm_async(
    message: AnyFormattedText = "Are you sure?",
    prefix: AnyFormattedText = FormattedText([(OneColors.CYAN, "❓ ")]),
    suffix: AnyFormattedText = FormattedText([(OneColors.LIGHT_YELLOW_b, " [Y/n] > ")]),
    session: PromptSession | None = None,
) -> bool:
    """Prompt the user with a yes/no async confirmation and return True for 'Y'."""
    session = session or PromptSession()
    merged_message: AnyFormattedText = merge_formatted_text([prefix, message, suffix])
    answer = await session.prompt_async(
        merged_message,
        validator=yes_no_validator(),
    )
    return answer.upper() == "Y"
