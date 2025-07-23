# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Utilities for user interaction prompts in the Falyx CLI framework.

Provides asynchronous confirmation dialogs and helper logic to determine
whether a user should be prompted based on command-line options.

Includes:
- `should_prompt_user()` for conditional prompt logic.
- `confirm_async()` for interactive yes/no confirmation.
"""

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import (
    AnyFormattedText,
    FormattedText,
    StyleAndTextTuples,
    merge_formatted_text,
)
from rich.console import Console
from rich.text import Text

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


def rich_text_to_prompt_text(text: Text | str | StyleAndTextTuples) -> StyleAndTextTuples:
    """
    Convert a Rich Text object to a list of (style, text) tuples
    compatible with prompt_toolkit.
    """
    if isinstance(text, list):
        if all(isinstance(pair, tuple) and len(pair) == 2 for pair in text):
            return text
        raise TypeError("Expected list of (style, text) tuples")

    if isinstance(text, str):
        text = Text.from_markup(text)

    if not isinstance(text, Text):
        raise TypeError("Expected str, rich.text.Text, or list of (style, text) tuples")

    console = Console(color_system=None, file=None, width=999, legacy_windows=False)
    segments = text.render(console)

    prompt_fragments: StyleAndTextTuples = []
    for segment in segments:
        style = segment.style or ""
        string = segment.text
        if string:
            prompt_fragments.append((str(style), string))
    return prompt_fragments
