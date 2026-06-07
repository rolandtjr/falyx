import sys

import pytest

from falyx import Falyx


async def test_run_quit_signal_exits_130(monkeypatch):
    flx = Falyx(default_to_menu=False)
    monkeypatch.setattr(sys, "argv", ["prog", "X"])

    with pytest.raises(SystemExit) as exc:
        await flx.run()

    assert exc.value.code == 130
