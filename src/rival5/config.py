"""The config file: the source of truth, since the mouse can't be read back."""

import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from rivalcfg.color_helpers import is_color, parse_color_string
from rivalcfg.devices.rival5 import profile
from rivalcfg.handlers.buttons import layout_multimedia, layout_qwerty
from rivalcfg.handlers.buttons.buttons import build_layout
from textual.color import Color, ColorParseError

MAX_PRESETS = 5
MIN_CPI, MAX_CPI, CPI_STEP = profile["settings"]["sensitivity"]["input_range"]
POLLING_RATES = list(profile["settings"]["polling_rate"]["choices"])
BRIGHTNESS_LEVELS = list(profile["settings"]["led_brightness"]["choices"])
STARTUP_MODES = list(profile["settings"]["default_lighting"]["choices"])
REACTIVE_OFF = ("off", "disable")

# Green LEDs are strong, so these names wash out when sent as their CSS values.
LED_COLORS = {"orange": "#ff4500", "pink": "#ff2850"}
DEFAULT_LED_COLOR = profile["settings"]["logo_color"]["default"]

LEFT_STRIP = ["z2", "z4", "z6", "z8"]
RIGHT_STRIP = ["z3", "z5", "z7", "z9"]
LEDS = ["z0", "z1", *LEFT_STRIP, *RIGHT_STRIP]
ZONES = {
    "all": LEDS,
    "left": LEFT_STRIP,
    "right": RIGHT_STRIP,
    "wheel": ["z0"],
    "logo": ["z1"],
    **{led: [led] for led in LEFT_STRIP + RIGHT_STRIP},
}
ZONE_ALIASES = {"z0": "wheel", "z1": "logo"}
PROFILE_NAME = re.compile(r"\w[\w -]{0,31}")

_BUTTONS = profile["settings"]["buttons_mapping"]["buttons"]
BUTTON_DEFAULTS = {name.lower(): info["default"] for name, info in _BUTTONS.items()}

# Button7-9 have id 0x00 in the device profile, so using them as an action would
# silently mean "disabled". Only offer what the mouse can really send.
MOUSE_ACTIONS = ["button1", "button2", "button3", "button4", "button5", "button6"]
SPECIAL_ACTIONS = ["disabled", "dpi", "scrollup", "scrolldown"]
MEDIA_KEYS = list(layout_multimedia.layout)
KEYBOARD_KEYS = list(layout_qwerty.layout)
_ACTIONS = {
    *MOUSE_ACTIONS,
    *SPECIAL_ACTIONS,
    "disable",
    *build_layout(layout_multimedia),
    *build_layout(layout_qwerty),
}


def default_path():
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "rival5" / "config.toml"


@dataclass
class Config:
    sensitivity: list = field(default_factory=lambda: [400, 800, 1200, 2400, 3200])
    polling: int = 1000
    brightness: int = 100
    startup: str = "rainbow"
    reactive: str = profile["settings"]["reactive_color"]["default"]
    rainbow: bool = False
    zones: dict = field(default_factory=dict)
    buttons: dict = field(default_factory=dict)


def validate(cfg, force=False):
    """Raise ValueError unless every value in cfg can be sent to the mouse."""
    presets = cfg.sensitivity
    if not 1 <= len(presets) <= MAX_PRESETS:
        raise ValueError(f"CPI needs 1 to {MAX_PRESETS} presets")
    for cpi in presets:
        if not isinstance(cpi, int) or not MIN_CPI <= cpi <= MAX_CPI or cpi % CPI_STEP:
            raise ValueError(
                f"CPI {cpi} must be {MIN_CPI}-{MAX_CPI} in steps of {CPI_STEP}"
            )
    if cfg.polling not in POLLING_RATES:
        raise ValueError(f"Polling rate must be one of {POLLING_RATES}")
    if cfg.brightness not in BRIGHTNESS_LEVELS:
        raise ValueError(f"Brightness must be one of {BRIGHTNESS_LEVELS}")
    if cfg.startup not in STARTUP_MODES:
        raise ValueError(f"Startup lighting must be one of {STARTUP_MODES}")
    check_reactive(cfg.reactive)
    for zone, color in cfg.zones.items():
        if zone not in ZONES:
            raise ValueError(f"Unknown zone: {zone}")
        parse_color(color)
    for button, action in cfg.buttons.items():
        if button not in BUTTON_DEFAULTS:
            raise ValueError(f"Unknown button: {button}")
        if action.lower() not in _ACTIONS:
            raise ValueError(f"Unknown action for {button}: {action}")
    if not force and not has_left_click(cfg.buttons):
        raise ValueError("No button would left-click. Bind one to button1")


def has_left_click(buttons):
    mapped = {**BUTTON_DEFAULTS, **buttons}
    return any(action.lower() == "button1" for action in mapped.values())


def set_zone(cfg, zone, color):
    """Set a zone's color, dropping narrower entries it now covers."""
    zone = ZONE_ALIASES.get(zone, zone)
    if zone not in ZONES:
        raise ValueError(f"Unknown zone: {zone}")
    parse_color(color)
    covered = set(ZONES[zone])
    cfg.zones = {
        name: value
        for name, value in cfg.zones.items()
        if not set(ZONES[name]) <= covered
    }
    cfg.zones[zone] = color
    cfg.rainbow = False


def resolve_zones(zones):
    """Return {led: color}, with narrow zones overriding broad ones."""
    leds = {}
    for name in sorted(zones, key=lambda zone: -len(ZONES[zone])):
        for led in ZONES[name]:
            leds[led] = zones[name]
    return leds


def parse_color(text):
    """Return (red, green, blue) for hex, a CSS color name, rgb() or hsl()."""
    if is_color(text):
        return parse_color_string(text)
    try:
        color = Color.parse(text.strip().lower())
    except ColorParseError as error:
        raise ValueError(f"Not a color: {text}") from error
    # Color.parse also takes things an LED can't show, like "ansi_red".
    if color.a != 1 or color.ansi is not None or color.auto:
        raise ValueError(f"Not a color: {text}")
    return color.rgb


def check_reactive(value):
    """Raise ValueError unless value is off or a color."""
    if value.lower() not in REACTIVE_OFF:
        parse_color(value)


def color_hex(color):
    red, green, blue = parse_color(color)
    return f"#{red:02x}{green:02x}{blue:02x}"


def led_hex(color):
    """Return the hex to send to the mouse, which can differ from the screen."""
    return LED_COLORS.get(color.strip().lower()) or color_hex(color)


def bind(cfg, button, action):
    """Bind one button, keeping every other binding."""
    button = button.lower()
    if button not in BUTTON_DEFAULTS:
        raise ValueError(f"Unknown button: {button}")
    if action.lower() == "default":
        cfg.buttons.pop(button, None)
    elif action.lower() not in _ACTIONS:
        raise ValueError(f"Unknown action for {button}: {action}")
    else:
        cfg.buttons[button] = action


def load(path=None):
    """Read and validate the config, or return defaults if there is none."""
    path = Path(path or default_path())
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except FileNotFoundError:
        return Config()
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{path}: {error}") from error

    defaults = Config()
    lighting = data.get("lighting", {})
    cfg = Config(
        sensitivity=data.get("sensitivity", {}).get("presets", defaults.sensitivity),
        polling=data.get("polling", {}).get("rate", defaults.polling),
        brightness=lighting.get("brightness", defaults.brightness),
        startup=lighting.get("startup", defaults.startup),
        reactive=lighting.get("reactive", defaults.reactive),
        rainbow=lighting.get("rainbow", defaults.rainbow),
        zones={ZONE_ALIASES.get(k, k): v for k, v in lighting.get("zones", {}).items()},
        buttons={k.lower(): v for k, v in data.get("buttons", {}).items()},
    )
    try:
        validate(cfg, force=True)
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError(f"{path}: {error}") from error
    return cfg


def profiles_dir():
    return default_path().parent / "profiles"


def profile_path(name):
    """Return the file for a profile. The name check also blocks other paths."""
    name = name.strip()
    if not PROFILE_NAME.fullmatch(name):
        raise ValueError(
            "Profile names are 1-32 letters, digits, spaces, - or _"
        )
    return profiles_dir() / f"{name}.toml"


def list_profiles():
    return sorted(path.stem for path in profiles_dir().glob("*.toml"))


def load_profile(name):
    path = profile_path(name)
    if not path.exists():
        raise ValueError(f"No profile named {name}")
    return load(path)


def delete_profile(name):
    profile_path(name).unlink(missing_ok=True)


def active_profile(cfg):
    """Return the name of a profile equal to cfg, or None."""
    for name in list_profiles():
        try:
            if load_profile(name) == cfg:
                return name
        except ValueError:
            continue
    return None


def _table(name, values):
    lines = [f"[{name}]"]
    lines += [f"{json.dumps(k)} = {json.dumps(v)}" for k, v in values.items()]
    return "\n".join(lines) + "\n"


def dumps(cfg):
    sections = [
        _table("sensitivity", {"presets": cfg.sensitivity}),
        _table("polling", {"rate": cfg.polling}),
        _table(
            "lighting",
            {
                "brightness": cfg.brightness,
                "startup": cfg.startup,
                "reactive": cfg.reactive,
                "rainbow": cfg.rainbow,
            },
        ),
        _table("lighting.zones", cfg.zones),
        _table("buttons", cfg.buttons),
    ]
    return "\n".join(sections)


def save(cfg, path=None):
    """Write the config atomically, so a crash can't leave half a file."""
    path = Path(path or default_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(dumps(cfg), encoding="utf-8")
    temporary.replace(path)
