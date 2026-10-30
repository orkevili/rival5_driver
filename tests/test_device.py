import pytest

from rival5 import device
from rival5.config import Config


def test_apply_sends_everything_then_saves(mouse):
    cfg = Config(zones={"all": "red"})
    device.apply(mouse, cfg)
    names = mouse.names()
    for name in (
        "set_sensitivity",
        "set_polling_rate",
        "set_buttons_mapping",
        "set_default_lighting",
        "set_led_brightness",
        "set_reactive_color",
        "set_logo_color",
    ):
        assert name in names
    assert names.index("save") < names.index("set_logo_color")


def test_apply_with_previous_sends_only_changes(mouse):
    previous = Config()
    cfg = Config(buttons={"button4": "F13"})
    device.apply(mouse, cfg, previous=previous)
    assert mouse.names() == ["set_buttons_mapping", "save"]


def test_apply_no_save(mouse):
    device.apply(mouse, Config(), save=False)
    assert "save" not in mouse.names()


def test_buttons_send_the_whole_override_map(mouse):
    device.send_buttons(mouse, Config(buttons={"button4": "F13", "button5": "a"}))
    assert mouse.calls == [
        ("set_buttons_mapping", {"buttons": {"button4": "F13", "button5": "a"}})
    ]


def test_restore_never_sends_cpi_or_saves(mouse):
    device.restore(mouse, Config(zones={"all": "red"}))
    assert "set_sensitivity" not in mouse.names()
    assert "save" not in mouse.names()
    assert "set_wheel_color" in mouse.names()


def test_rainbow_wins_over_zones(mouse):
    device.send_lighting(mouse, Config(rainbow=True, zones={"all": "red"}))
    assert mouse.names() == ["set_rainbow_effect"]


def test_status_reads_sysfs(tmp_path, monkeypatch):
    monkeypatch.delenv("RIVALCFG_DRY")
    assert device.status(tmp_path) == device.MISSING

    usb = tmp_path / "3-1"
    usb.mkdir()
    (usb / "idVendor").write_text("1038\n")
    (usb / "idProduct").write_text("183c\n")
    (usb / "busnum").write_text("3\n")
    (usb / "devnum").write_text("3\n")
    monkeypatch.setattr(device.os, "access", lambda *_: False)
    assert device.status(tmp_path) == device.FORBIDDEN
    monkeypatch.setattr(device.os, "access", lambda *_: True)
    assert device.status(tmp_path) == device.CONNECTED


def test_status_ignores_other_steelseries_devices(tmp_path, monkeypatch):
    monkeypatch.delenv("RIVALCFG_DRY")
    usb = tmp_path / "3-2"
    usb.mkdir()
    (usb / "idVendor").write_text("1038\n")
    (usb / "idProduct").write_text("1622\n")
    assert device.status(tmp_path) == device.MISSING


def test_open_mouse_missing(monkeypatch):
    monkeypatch.delenv("RIVALCFG_DRY")
    monkeypatch.setattr(device.usbhid, "is_device_plugged", lambda *_: False)
    with pytest.raises(device.DeviceError, match="not found"):
        device.open_mouse()


def test_open_mouse_permission(monkeypatch):
    def refuse(*_):
        raise OSError("open failed")

    monkeypatch.delenv("RIVALCFG_DRY")
    monkeypatch.setattr(device.usbhid, "is_device_plugged", lambda *_: True)
    monkeypatch.setattr(device, "get_mouse", refuse)
    with pytest.raises(device.DeviceError, match="install.sh"):
        device.open_mouse()


def test_real_rivalcfg_encodes_a_full_config():
    """Run the real encoders, including keys rivalcfg's strings can't express."""
    cfg = Config(
        sensitivity=[400, 1600],
        zones={"all": "#00aaff", "wheel": "red"},
        buttons={"button4": "F13", "button5": "PlayPause", "button6": ";"},
    )
    with device.open_mouse() as real:
        device.apply(real, cfg)
        written = bytes(real._hid_device.bytes.getvalue())
    assert bytes([0x51, 0x68]) in written  # F13
    assert bytes([0x61, 0xCD]) in written  # PlayPause
    assert bytes([0x11, 0x00]) in written  # save


def test_named_colors_reach_rivalcfg_as_hex(mouse):
    cfg = Config(zones={"logo": "orange"}, reactive="hotpink")
    device.send_lighting(mouse, cfg)
    device.send_reactive(mouse, cfg)
    assert mouse.calls == [
        ("set_logo_color", "#ff4500"),
        ("set_reactive_color", "#ff69b4"),
    ]


def test_reactive_off_is_sent_as_off(mouse):
    device.send_reactive(mouse, Config(reactive="off"))
    assert mouse.calls == [("set_reactive_color", "off")]


def test_send_lighting_skips_leds_already_showing_the_color(mouse):
    first = Config(zones={"all": "red"})
    last_sent = device.send_lighting(mouse, first)
    mouse.calls.clear()
    device.send_lighting(mouse, Config(zones={"all": "red", "logo": "blue"}), last_sent)
    assert mouse.calls == [("set_logo_color", "#0000ff")]


def test_rainbow_means_nothing_can_be_skipped(mouse):
    assert device.send_lighting(mouse, Config(rainbow=True)) is None


def test_lighting_waits_for_the_flash_write_after_a_save(mouse, monkeypatch):
    monkeypatch.setattr(device, "SAVE_PAUSE", 0.3)
    monkeypatch.setattr(
        device.time, "sleep", lambda seconds: mouse.calls.append(("sleep", seconds))
    )
    device.apply(mouse, Config(zones={"wheel": "red"}))
    names = mouse.names()
    assert names.index("save") < names.index("sleep") < names.index("set_wheel_color")
    assert ("sleep", 0.3) in mouse.calls


def test_no_pause_without_a_save(mouse, monkeypatch):
    monkeypatch.setattr(
        device.time, "sleep", lambda seconds: mouse.calls.append(("sleep", seconds))
    )
    device.apply(mouse, Config(zones={"wheel": "red"}), save=False)
    assert "sleep" not in mouse.names()
