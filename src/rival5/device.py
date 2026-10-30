"""Talk to the mouse through rivalcfg."""

import os
from pathlib import Path

from rivalcfg import usbhid
from rivalcfg.mouse import get_mouse

from . import config

VENDOR_ID = 0x1038
PRODUCT_IDS = (0x183C, 0x183E)

NOT_FOUND = "Rival 5 not found. Is it plugged in?"
NO_PERMISSION = (
    "No permission to open the mouse. Run install.sh, then replug it."
)

CONNECTED, MISSING, FORBIDDEN = "connected", "not connected", "no permission"

_LED_SETTINGS = {"z0": "wheel_color", "z1": "logo_color"}


class DeviceError(Exception):
    pass


def open_mouse():
    """Open the mouse, for use as a context manager."""
    for product_id in PRODUCT_IDS:
        if "RIVALCFG_DRY" in os.environ or usbhid.is_device_plugged(
            VENDOR_ID, product_id
        ):
            try:
                return get_mouse(VENDOR_ID, product_id)
            except usbhid.DeviceNotFound as error:
                raise DeviceError(NOT_FOUND) from error
            except OSError as error:
                raise DeviceError(NO_PERMISSION) from error
    raise DeviceError(NOT_FOUND)


def status(usb_devices=Path("/sys/bus/usb/devices")):
    """Report the state without opening the mouse.

    Opening detaches the kernel driver from interface 0, which is too
    disruptive to do on a timer.
    """
    if "RIVALCFG_DRY" in os.environ:
        return CONNECTED
    wanted = {f"{product_id:04x}" for product_id in PRODUCT_IDS}
    for path in usb_devices.glob("*"):
        try:
            if (path / "idVendor").read_text().strip() != f"{VENDOR_ID:04x}":
                continue
            if (path / "idProduct").read_text().strip() not in wanted:
                continue
            bus = int((path / "busnum").read_text())
            address = int((path / "devnum").read_text())
        except OSError:
            continue
        node = f"/dev/bus/usb/{bus:03d}/{address:03d}"
        return CONNECTED if os.access(node, os.W_OK) else FORBIDDEN
    return MISSING


def send_buttons(mouse, cfg):
    # A dict skips rivalcfg's string syntax, which can't express keys like ";".
    # It also needs every override at once: unlisted buttons reset to defaults.
    mouse.set_buttons_mapping({"buttons": dict(cfg.buttons)})


def send_lighting(mouse, cfg, last_sent=None):
    """Send the colors, skipping LEDs that already show them.

    Each write takes a while, so a preview only sends what changed. Returns
    what to pass as last_sent next time; rainbow means nothing can be skipped.
    """
    if cfg.rainbow:
        mouse.set_rainbow_effect()
        return None
    showing = dict(last_sent or {})
    for led, color in config.resolve_zones(cfg.zones).items():
        color = config.led_hex(color)
        if showing.get(led) != color:
            setting = _LED_SETTINGS.get(led, f"{led}_color")
            getattr(mouse, f"set_{setting}")(color)
            showing[led] = color
    return showing


def send_reactive(mouse, cfg):
    reactive = cfg.reactive
    if reactive.lower() not in config.REACTIVE_OFF:
        reactive = config.led_hex(reactive)
    mouse.set_reactive_color(reactive)


def apply(mouse, cfg, previous=None, save=True):
    """Send cfg to the mouse, or only what differs from previous.

    CPI is skipped when unchanged because writing it resets the active preset.
    """

    def changed(*names):
        return previous is None or any(
            getattr(cfg, name) != getattr(previous, name) for name in names
        )

    if changed("sensitivity"):
        mouse.set_sensitivity(cfg.sensitivity)
    if changed("polling"):
        mouse.set_polling_rate(cfg.polling)
    if changed("buttons"):
        send_buttons(mouse, cfg)
    if changed("startup"):
        mouse.set_default_lighting(cfg.startup)
    if changed("brightness"):
        mouse.set_led_brightness(cfg.brightness)
    if changed("reactive"):
        send_reactive(mouse, cfg)
    if save:
        mouse.save()
    if changed("zones", "rainbow"):
        send_lighting(mouse, cfg)


def restore(mouse, cfg):
    """Re-send what the mouse forgets. Never touches CPI."""
    mouse.set_led_brightness(cfg.brightness)
    send_reactive(mouse, cfg)
    send_lighting(mouse, cfg)


def reset(mouse):
    mouse.reset_settings()
    mouse.save()
