import pytest

from rival5 import config
from rival5.config import Config


def test_missing_file_gives_defaults():
    assert config.load() == Config()


def test_round_trip():
    cfg = Config(
        sensitivity=[400, 1600],
        polling=500,
        brightness=75,
        startup="off",
        reactive="#ffffff",
        zones={"all": "#00aaff", "wheel": "red"},
        buttons={"button4": "F13", "button5": ";", "button6": "[", "button2": "\\"},
    )
    config.save(cfg)
    assert config.load() == cfg


def test_rainbow_round_trip():
    cfg = Config(rainbow=True)
    config.save(cfg)
    assert config.load().rainbow is True


def test_broken_file_names_the_path():
    path = config.default_path()
    path.parent.mkdir(parents=True)
    path.write_text("[polling\n")
    with pytest.raises(ValueError, match="config.toml"):
        config.load()


@pytest.mark.parametrize(
    "broken",
    [
        Config(sensitivity=[]),
        Config(sensitivity=[100] * 6),
        Config(sensitivity=[50]),
        Config(sensitivity=[18100]),
        Config(sensitivity=[450]),
        Config(polling=999),
        Config(brightness=60),
        Config(startup="blue"),
        Config(reactive="notacolor"),
        Config(zones={"nope": "red"}),
        Config(zones={"all": "notacolor"}),
        Config(buttons={"button99": "a"}),
        Config(buttons={"button4": "notakey"}),
    ],
)
def test_validate_rejects(broken):
    with pytest.raises(ValueError):
        config.validate(broken)


def test_validate_accepts_defaults():
    config.validate(Config())


def test_refuses_config_with_no_left_click():
    cfg = Config(buttons={"button1": "a"})
    with pytest.raises(ValueError, match="left-click"):
        config.validate(cfg)
    config.validate(cfg, force=True)


def test_swapped_clicks_still_have_left_click():
    config.validate(Config(buttons={"button1": "button2", "button2": "button1"}))


def test_button_7_to_9_are_not_actions():
    for name in ("button7", "button8", "button9"):
        with pytest.raises(ValueError):
            config.bind(Config(), "button4", name)


def test_bind_keeps_other_bindings():
    cfg = Config()
    config.bind(cfg, "button4", "F13")
    config.bind(cfg, "Button5", "PlayPause")
    assert cfg.buttons == {"button4": "F13", "button5": "PlayPause"}


def test_bind_default_removes_override():
    cfg = Config(buttons={"button4": "F13"})
    config.bind(cfg, "button4", "default")
    assert cfg.buttons == {}


def test_resolve_zones_narrow_overrides_broad():
    leds = config.resolve_zones({"wheel": "red", "left": "lime", "all": "blue"})
    assert len(leds) == 10
    assert leds["z0"] == "red"
    assert leds["z2"] == "lime"
    assert leds["z3"] == "blue"


def test_set_zone_drops_covered_zones():
    cfg = Config(zones={"z2": "red", "left": "lime", "right": "blue"})
    config.set_zone(cfg, "left", "white")
    assert cfg.zones == {"right": "blue", "left": "white"}
    config.set_zone(cfg, "all", "black")
    assert cfg.zones == {"all": "black"}


def test_set_zone_alias_and_clears_rainbow():
    cfg = Config(rainbow=True)
    config.set_zone(cfg, "z1", "red")
    assert cfg.zones == {"logo": "red"}
    assert cfg.rainbow is False


def test_color_hex():
    assert config.color_hex("red") == "#ff0000"
    assert config.color_hex("#0AF") == "#00aaff"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("orange", (255, 165, 0)),
        ("Orange", (255, 165, 0)),
        ("hotpink", (255, 105, 180)),
        ("rgb(1,2,3)", (1, 2, 3)),
        ("hsl(30,100%,50%)", (255, 128, 0)),
        ("0af", (0, 170, 255)),
        ("#00aaff", (0, 170, 255)),
        ("green", (0, 128, 0)),
    ],
)
def test_parse_color(text, expected):
    assert config.parse_color(text) == expected


@pytest.mark.parametrize(
    "text",
    ["ansi_red", "transparent", "auto", "red 50%", "rgba(1,2,3,0.5)", "nope", ""],
)
def test_parse_color_rejects_what_an_led_cannot_show(text):
    with pytest.raises(ValueError):
        config.parse_color(text)


def test_named_color_stays_as_typed_in_the_file():
    cfg = Config()
    config.set_zone(cfg, "all", "orange")
    config.save(cfg)
    assert config.load().zones == {"all": "orange"}


@pytest.mark.parametrize("value", ["off", "OFF", "disable", "orange"])
def test_reactive_accepts(value):
    config.check_reactive(value)


def test_led_colors_differ_from_the_screen_only_for_tuned_names():
    assert config.color_hex("orange") == "#ffa500"
    assert config.led_hex("Orange") == "#ff4500"
    assert config.led_hex("pink") == "#ff2850"
    assert config.led_hex("#ffa500") == "#ffa500"
    assert config.led_hex("hotpink") == "#ff69b4"
