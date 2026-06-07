# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Display types for Falyx.

This module defines data models used for representing styled display elements in
Falyx's CLI output, such as command paths, namespaces, and TLDR examples. These
models are designed to be simple containers for the raw text and styling
information needed to render consistent and visually appealing CLI interfaces using
the Rich library.

It provides:
    - `StyledSegment` for representing a single styled token.
"""
from pydantic import BaseModel, ConfigDict
from rich.style import Style


class StyledSegment(BaseModel):
    """Styled path segment used to build Rich styled markup.

    `StyledSegment` represents a single token. It stores the raw display
    text and an optional Rich style so text can be rendered either
    as plain text or styled markup.

    Attributes:
        text (str): Display text for this path segment.
        style (str | None): Optional Rich style applied when rendering this
            segment in markup output.
    """

    text: str
    style: Style | str | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)
