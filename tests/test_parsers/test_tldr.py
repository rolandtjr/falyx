import pytest

from falyx.exceptions import CommandArgumentError
from falyx.parser.command_argument_parser import CommandArgumentParser


@pytest.mark.asyncio
async def test_add_tldr_examples():
    parser = CommandArgumentParser()
    parser.add_tldr_examples(
        [
            ("example1", "This is the first example."),
            ("example2", "This is the second example."),
        ]
    )
    assert len(parser._tldr_examples) == 2
    assert parser._tldr_examples[0].usage == "example1"
    assert parser._tldr_examples[0].description == "This is the first example."
    assert parser._tldr_examples[1].usage == "example2"
    assert parser._tldr_examples[1].description == "This is the second example."


@pytest.mark.asyncio
async def test_bad_tldr_examples():
    parser = CommandArgumentParser()
    with pytest.raises(CommandArgumentError):
        parser.add_tldr_examples(
            [
                ("example1", "This is the first example.", "extra_arg"),
                ("example2", "This is the second example."),
            ]
        )


@pytest.mark.asyncio
async def test_add_tldr_examples_in_init():
    parser = CommandArgumentParser(
        tldr_examples=[
            ("example1", "This is the first example."),
            ("example2", "This is the second example."),
        ]
    )
    assert len(parser._tldr_examples) == 2
    assert parser._tldr_examples[0].usage == "example1"
    assert parser._tldr_examples[0].description == "This is the first example."
    assert parser._tldr_examples[1].usage == "example2"
    assert parser._tldr_examples[1].description == "This is the second example."
