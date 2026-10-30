"""See mouse button presses, by reading the mouse's own hidraw nodes.

The mouse reports the action a button performs, not which button it was, so
presses are given as action names to look up in the bindings. A disabled button
reports nothing.
"""

import asyncio
import os
from pathlib import Path

from rivalcfg.handlers.buttons import layout_multimedia, layout_qwerty
from rivalcfg.handlers.buttons.buttons import build_layout

from . import device

MOUSE, KEYBOARD = "input1", "input3"
KEY_REPORT, MEDIA_REPORT = 1, 2
FIRST_MODIFIER = 0xE0
REPORT_SIZE = 64

_KEY_CODES = build_layout(layout_qwerty)
_MEDIA_CODES = build_layout(layout_multimedia)
_KEY_NAMES = {code: name for name, code in layout_qwerty.layout.items()}
_MEDIA_NAMES = {code: name for name, code in layout_multimedia.layout.items()}


def canonical(action):
    """Give an action the name a report uses, resolving case and aliases."""
    lowered = action.lower()
    if lowered in _KEY_CODES:
        return _KEY_NAMES[_KEY_CODES[lowered]]
    if lowered in _MEDIA_CODES:
        return _MEDIA_NAMES[_MEDIA_CODES[lowered]]
    return lowered


def find_nodes(hidraw_root=Path("/sys/class/hidraw")):
    """Return the hidraw paths of the mouse's interfaces, by interface."""
    if "RIVALCFG_DRY" in os.environ:
        return {}
    wanted = {
        f"HID_ID=0003:{device.VENDOR_ID:08X}:{product_id:08X}"
        for product_id in device.PRODUCT_IDS
    }
    nodes = {}
    for path in hidraw_root.glob("hidraw*"):
        try:
            lines = (path / "device" / "uevent").read_text().splitlines()
        except OSError:
            continue
        if wanted.isdisjoint(lines):
            continue
        for interface in (MOUSE, KEYBOARD):
            if any(
                line.startswith("HID_PHYS=") and line.endswith(f"/{interface}")
                for line in lines
            ):
                nodes[interface] = Path("/dev") / path.name
    return nodes


def _bits(data):
    value = int.from_bytes(data)
    return [bit for bit in range(8) if value >> bit & 1]


def _held(interface, report):
    if interface == MOUSE:
        return [f"button{bit + 1}" for bit in _bits(report[:1])]
    if report[:1] == bytes([KEY_REPORT]):
        modifiers = [FIRST_MODIFIER + bit for bit in _bits(report[1:2])]
        codes = [*modifiers, *report[3:]]
        return [_KEY_NAMES[code] for code in codes if code in _KEY_NAMES]
    if report[:1] == bytes([MEDIA_REPORT]):
        codes = [int.from_bytes(report[at:at + 2], "little") for at in (1, 3)]
        return [_MEDIA_NAMES[code] for code in codes if code in _MEDIA_NAMES]
    return []


def pressed_actions(interface, report, previous=b""):
    """Return what is held in report but wasn't in the one before it."""
    before = _held(interface, previous)
    return [action for action in _held(interface, report) if action not in before]


class ButtonWatch:
    """Call back with the action of each press, until closed.

    Runs on the asyncio loop it is created on, without a thread.
    """

    def __init__(self, callback, nodes=None):
        self.callback = callback
        self.loop = asyncio.get_running_loop()
        self.files = {}
        self.last = {}
        self.closed = False
        for interface, path in (find_nodes() if nodes is None else nodes).items():
            try:
                descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            self.files[interface] = descriptor
            self.loop.add_reader(descriptor, self._read, interface)
        if not self.files:
            raise OSError("No button reports available")

    def _read(self, interface):
        try:
            report = os.read(self.files[interface], REPORT_SIZE)
        except BlockingIOError:
            return
        except OSError:
            report = b""
        if not report:
            self.close()
            return
        # Key and media reports take turns, and each only updates its own state.
        slot = (interface, report[:1] if interface == KEYBOARD else b"")
        actions = pressed_actions(interface, report, self.last.get(slot, b""))
        self.last[slot] = report
        for action in actions:
            self.callback(action)

    def close(self):
        self.closed = True
        for descriptor in self.files.values():
            self.loop.remove_reader(descriptor)
            os.close(descriptor)
        self.files = {}
