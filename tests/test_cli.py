import pytest

from rival5 import cli, config, device


@pytest.fixture
def fake(mouse, monkeypatch):
    monkeypatch.setattr(device, "open_mouse", lambda: mouse)
    return mouse


def test_bind_accumulates(fake):
    assert cli.main(["bind", "button4=F13"]) == 0
    assert cli.main(["bind", "button5=PlayPause"]) == 0
    assert config.load().buttons == {"button4": "F13", "button5": "PlayPause"}
    assert fake.calls[-2] == (
        "set_buttons_mapping",
        {"buttons": {"button4": "F13", "button5": "PlayPause"}},
    )
    assert fake.calls[-1] == ("save",)


def test_bind_key_containing_equals(fake):
    assert cli.main(["bind", "button4=="]) == 0
    assert config.load().buttons == {"button4": "="}


def test_no_save_touches_neither_config_nor_memory(fake):
    assert cli.main(["--no-save", "bind", "button4=a"]) == 0
    assert "save" not in fake.names()
    assert not config.default_path().exists()


def test_bind_refuses_losing_left_click(fake, capsys):
    assert cli.main(["bind", "button1=a"]) == 1
    assert "left-click" in capsys.readouterr().err
    assert fake.calls == []
    assert cli.main(["bind", "--force", "button1=a"]) == 0


def test_invalid_value_sends_nothing(fake, capsys):
    assert cli.main(["cpi", "450"]) == 1
    assert fake.calls == []
    assert not config.default_path().exists()


def test_failed_send_leaves_config_alone(monkeypatch, capsys):
    def missing():
        raise device.DeviceError(device.NOT_FOUND)

    monkeypatch.setattr(device, "open_mouse", missing)
    assert cli.main(["cpi", "800"]) == 1
    assert "not found" in capsys.readouterr().err
    assert not config.default_path().exists()


def test_color_is_not_saved_onboard(fake):
    assert cli.main(["color", "all", "red"]) == 0
    assert "save" not in fake.names()
    assert config.load().zones == {"all": "red"}


def test_rainbow(fake):
    assert cli.main(["rainbow"]) == 0
    assert fake.names() == ["set_rainbow_effect"]
    assert config.load().rainbow is True


def test_cpi_poll_brightness(fake):
    assert cli.main(["cpi", "400", "800"]) == 0
    assert cli.main(["poll", "500"]) == 0
    assert cli.main(["brightness", "50"]) == 0
    cfg = config.load()
    assert (cfg.sensitivity, cfg.polling, cfg.brightness) == ([400, 800], 500, 50)
    assert fake.names().count("save") == 3


def test_unbind(fake):
    cli.main(["bind", "button4=a", "button5=b"])
    assert cli.main(["unbind", "button4"]) == 0
    assert config.load().buttons == {"button5": "b"}
    assert cli.main(["unbind", "--all"]) == 0
    assert config.load().buttons == {}
    assert cli.main(["unbind"]) == 1


def test_restore_without_config_does_nothing(fake):
    assert cli.main(["restore"]) == 0
    assert fake.calls == []


def test_restore_is_quiet_when_mouse_is_missing(monkeypatch):
    def missing():
        raise device.DeviceError(device.NOT_FOUND)

    config.save(config.Config())
    monkeypatch.setattr(device, "open_mouse", missing)
    assert cli.main(["restore"]) == 0


def test_restore_reports_permission_problem(monkeypatch):
    def forbidden():
        raise device.DeviceError(device.NO_PERMISSION)

    config.save(config.Config())
    monkeypatch.setattr(device, "open_mouse", forbidden)
    assert cli.main(["restore"]) == 1


def test_reset_clears_config(fake):
    cli.main(["bind", "button4=a"])
    assert cli.main(["reset"]) == 0
    assert "reset_settings" in fake.names()
    assert not config.default_path().exists()


def test_show_says_it_is_the_config(capsys):
    assert cli.main(["show"]) == 0
    assert "can't be read back" in capsys.readouterr().out
