import asyncio
import os
from pathlib import Path

import pytest

from rival5.buttonwatch import (
    KEYBOARD,
    MOUSE,
    ButtonWatch,
    canonical,
    find_nodes,
    pressed_actions,
)

F13 = 104
MUTE = 226


def mouse_report(buttons=0, x=0):
    return bytes([buttons]) + x.to_bytes(2, "little") + bytes(3)


def key_report(*codes, modifiers=0):
    return bytes([1, modifiers, 0, *codes]) + bytes(6 - len(codes))


def media_report(code=0):
    return bytes([2]) + code.to_bytes(2, "little") + bytes(2)


def add_hidraw(root, name, hid_id, phys):
    path = root / name / "device"
    path.mkdir(parents=True)
    (path / "uevent").write_text(f"HID_ID={hid_id}\nHID_PHYS={phys}\n")


def test_find_nodes_picks_the_rival_interfaces(tmp_path, monkeypatch):
    monkeypatch.delenv("RIVALCFG_DRY")
    rival = "0003:00001038:0000183C"
    add_hidraw(tmp_path, "hidraw2", rival, "usb-0000:35:00.4-1/input0")
    add_hidraw(tmp_path, "hidraw3", rival, "usb-0000:35:00.4-1/input1")
    add_hidraw(tmp_path, "hidraw5", rival, "usb-0000:35:00.4-1/input3")
    add_hidraw(tmp_path, "hidraw9", "0003:00001038:00001622", "usb-1/input1")
    assert find_nodes(tmp_path) == {
        MOUSE: Path("/dev/hidraw3"),
        KEYBOARD: Path("/dev/hidraw5"),
    }


def test_find_nodes_reads_nothing_in_a_dry_run(tmp_path):
    add_hidraw(tmp_path, "hidraw3", "0003:00001038:0000183C", "usb-1/input1")
    assert find_nodes(tmp_path) == {}


def test_press_counts_once():
    pressed = mouse_report(0b1000)
    assert pressed_actions(MOUSE, pressed) == ["button4"]
    assert pressed_actions(MOUSE, mouse_report(0b1000, x=5), pressed) == []
    assert pressed_actions(MOUSE, mouse_report(), pressed) == []


def test_second_button_while_one_is_held():
    held = mouse_report(0b001)
    assert pressed_actions(MOUSE, mouse_report(0b011), held) == ["button2"]


def test_movement_is_not_a_press():
    assert pressed_actions(MOUSE, mouse_report(x=300)) == []


def test_key_and_modifier_reports():
    assert pressed_actions(KEYBOARD, key_report(F13)) == ["F13"]
    assert pressed_actions(KEYBOARD, key_report(modifiers=1)) == ["LeftCtrl"]
    assert pressed_actions(KEYBOARD, key_report(F13), key_report(F13)) == []


def test_media_report_is_not_read_as_a_key():
    assert pressed_actions(KEYBOARD, media_report(MUTE)) == ["Mute"]
    assert pressed_actions(KEYBOARD, media_report()) == []


@pytest.mark.parametrize("report", [b"", b"\x01", b"\x02", b"\x07\x01"])
def test_short_or_unknown_reports_are_ignored(report):
    assert pressed_actions(KEYBOARD, report) == []


@pytest.mark.parametrize(
    "action, expected",
    [
        ("BUTTON4", "button4"),
        ("f13", "F13"),
        ("pgup", "PageUp"),
        ("vol+", "VolumeUp"),
        ("disabled", "disabled"),
    ],
)
def test_canonical(action, expected):
    assert canonical(action) == expected


async def collect_presses(nodes, reports):
    """Feed reports through fifos and return what the watch saw."""
    seen = []
    writers = {}
    for interface, path in nodes.items():
        os.mkfifo(path)
        writers[interface] = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    watch = ButtonWatch(seen.append, nodes)
    try:
        for interface, report in reports:
            os.write(writers[interface], report)
            await asyncio.sleep(0.01)
        return seen, watch
    finally:
        for writer in writers.values():
            os.close(writer)


async def test_watch_reports_each_press(tmp_path):
    nodes = {MOUSE: tmp_path / "mouse", KEYBOARD: tmp_path / "keys"}
    seen, watch = await collect_presses(
        nodes,
        [
            (MOUSE, mouse_report(0b1)),
            (MOUSE, mouse_report(0b1, x=2)),
            (MOUSE, mouse_report()),
            (KEYBOARD, key_report(F13)),
            (KEYBOARD, media_report(MUTE)),
            (KEYBOARD, key_report(F13)),
            (KEYBOARD, media_report()),
            (KEYBOARD, key_report()),
        ],
    )
    watch.close()
    assert seen == ["button1", "F13", "Mute"]


async def test_watch_closes_when_the_node_goes_away(tmp_path):
    path = tmp_path / "mouse"
    os.mkfifo(path)
    writer = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    watch = ButtonWatch(lambda action: None, {MOUSE: path})
    os.close(writer)
    await asyncio.sleep(0.01)
    assert watch.closed
    assert watch.files == {}


async def test_watch_skips_an_interface_it_cannot_open(tmp_path):
    good = tmp_path / "mouse"
    os.mkfifo(good)
    writer = os.open(good, os.O_RDWR | os.O_NONBLOCK)
    watch = ButtonWatch(
        lambda action: None, {MOUSE: good, KEYBOARD: tmp_path / "missing"}
    )
    assert list(watch.files) == [MOUSE]
    watch.close()
    os.close(writer)


async def test_watch_fails_with_nothing_to_read():
    with pytest.raises(OSError):
        ButtonWatch(lambda action: None, {})
