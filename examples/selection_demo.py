import asyncio

from falyx.selection import (
    SelectionOption,
    prompt_for_selection,
    render_selection_dict_table,
)

menu = {
    "A": SelectionOption("Run diagnostics", lambda: print("Running diagnostics...")),
    "B": SelectionOption("Deploy to staging", lambda: print("Deploying...")),
}

table = render_selection_dict_table(
    title="Main Menu",
    selections=menu,
)

key = asyncio.run(prompt_for_selection(menu.keys(), table))
print(f"You selected: {key}")

menu[key.upper()].value()
