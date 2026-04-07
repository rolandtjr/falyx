import sys

import pytest

from falyx import Falyx


@pytest.mark.asyncio
async def test_run_basic(capsys):
    sys.argv = ["falyx", "-h"]
    flx = Falyx()
    with pytest.raises(SystemExit):
        await flx.run()

    captured = capsys.readouterr()
    assert "Show this help menu." in captured.out
