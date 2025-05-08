from falyx.options_manager import OptionsManager


def should_prompt_user(
    *,
    confirm: bool,
    options: OptionsManager,
    namespace: str = "cli_args",
):
    """Determine whether to prompt the user for confirmation based on command and global options."""
    never_prompt = options.get("never_prompt", False, namespace)
    force_confirm = options.get("force_confirm", False, namespace)
    skip_confirm = options.get("skip_confirm", False, namespace)

    if never_prompt or skip_confirm:
        return False

    return confirm or force_confirm
