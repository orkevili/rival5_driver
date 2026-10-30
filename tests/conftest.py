import pytest


class FakeMouse:
    """Records every setter call, in order."""

    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def __getattr__(self, name):
        if not (name.startswith("set_") or name in ("save", "reset_settings")):
            raise AttributeError(name)

        def record(*args):
            self.calls.append((name, *args))

        return record

    def names(self):
        return [call[0] for call in self.calls]


@pytest.fixture
def mouse():
    return FakeMouse()


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep rival5 and rivalcfg away from the real config and mouse."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("RIVALCFG_DRY", "1")
    monkeypatch.setenv("RIVALCFG_DEBUG_NO_COMMAND_DELAY", "1")
