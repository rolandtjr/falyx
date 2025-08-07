import sys

import pytest

from falyx import Falyx
from falyx.parser import get_arg_parsers


@pytest.mark.asyncio
async def test_run_basic(capsys):
    sys.argv = ["falyx", "run", "-h"]
    falyx_parsers = get_arg_parsers()
    assert falyx_parsers is not None, "Falyx parsers should be initialized"
    flx = Falyx()
    with pytest.raises(SystemExit):
        await flx.run(falyx_parsers)

    captured = capsys.readouterr()
    assert "Run a command by its key or alias." in captured.out
