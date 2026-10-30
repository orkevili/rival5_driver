import threading

from textual.widgets import Input

from rival5 import config, device
from rival5.colorpicker import ColorField, ColorPicker, HueBar
from rival5.config import Config
from rival5.tui import Rival5App


def make_app(mouse):
    return Rival5App(opener=lambda: mouse, status=lambda: device.CONNECTED)


async def settle(app, pilot):
    await app.workers.wait_for_complete()
    await pilot.pause()


class GatedMouse:
    """Holds the first write back, so more previews can queue behind it."""

    def __init__(self, mouse):
        self.mouse = mouse
        self.gate = threading.Event()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def __getattr__(self, name):
        self.gate.wait(5)
        return getattr(self.mouse, name)


async def test_p_opens_picker_at_the_zone_color(mouse):
    config.save(Config(zones={"all": "#ff0000"}))
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.press("p")
        assert isinstance(app.screen, ColorPicker)
        assert app.screen.color == "#ff0000"


async def test_arrows_preview_and_enter_keeps_the_color(mouse):
    config.save(Config(zones={"all": "#ff0000"}))
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.press("p", "down", "left", "enter")
        await settle(app, pilot)
        assert not isinstance(app.screen, ColorPicker)
        assert app.cfg.zones["all"] not in ("#ff0000", "red")
        assert "set_logo_color" in mouse.names()
        assert "save" not in mouse.names()
        assert app.dirty


async def test_hue_keys_work_without_altgr(mouse):
    config.save(Config(zones={"all": "#ff0000"}))
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.press("p", "full_stop")
        assert app.screen.hue > 0
        await pilot.press("comma")
        assert app.screen.hue == 0


async def test_escape_restores_the_previous_color(mouse):
    config.save(Config(zones={"all": "#ff0000", "wheel": "#0000ff"}))
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.press("p", "down", "down", "escape")
        await settle(app, pilot)
        assert app.cfg.zones == {"all": "#ff0000", "wheel": "#0000ff"}
        assert not app.dirty
        assert mouse.calls[-1][1] in ("#ff0000", "#0000ff")
        assert app.query_one("#color", Input).value == "#ff0000"


async def test_click_on_field_and_bar_changes_the_color(mouse):
    config.save(Config(zones={"all": "#ff0000"}))
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.press("p")
        await pilot.click(ColorField, offset=(0, 0))
        assert app.screen.color == "#ffffff"
        await pilot.click(ColorField, offset=(33, 0))
        assert app.screen.color == "#ff0000"
        await pilot.click(HueBar, offset=(11, 0))
        assert 0.3 < app.screen.hue < 0.35


async def test_mouse_position_is_clamped(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.press("p")
        app.screen.query_one(ColorField).pick(500, -3)
        assert (app.screen.saturation, app.screen.value) == (1.0, 1.0)


async def test_black_keeps_the_arrows_usable(mouse):
    config.save(Config(zones={"all": "#000000"}))
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.press("p", "up", "right")
        assert app.screen.value > 0


async def test_reactive_picker_previews_and_escape_restores_off(mouse):
    config.save(Config(reactive="off"))
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.click("#pick-reactive")
        assert isinstance(app.screen, ColorPicker)
        await pilot.press("down")
        await settle(app, pilot)
        assert app.cfg.reactive != "off"
        await pilot.press("escape")
        await settle(app, pilot)
        assert app.cfg.reactive == "off"
        assert mouse.calls[-1] == ("set_reactive_color", "off")
        assert not app.dirty


async def test_reactive_enter_previews_without_saving(mouse):
    config.save(Config(reactive="off"))
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        app.query_one("#reactive", Input).focus()
        app.query_one("#reactive", Input).value = ""
        await pilot.press(*"red", "enter")
        await settle(app, pilot)
        assert ("set_reactive_color", "#ff0000") in mouse.calls
        assert "save" not in mouse.names()
        assert not config.default_path().exists() or config.load().reactive == "off"


async def test_discard_restores_a_previewed_reactive_color(mouse):
    config.save(Config(reactive="off"))
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        app.query_one("#reactive", Input).focus()
        app.query_one("#reactive", Input).value = ""
        await pilot.press(*"red", "enter")
        await settle(app, pilot)
        app.query_one("#zones").focus()
        await pilot.press("q")
        await pilot.pause()
        await pilot.click("#discard")
        await settle(app, pilot)
        assert mouse.calls[-1] == ("set_reactive_color", "off")


async def test_save_sends_reactive_when_preview_left_the_mouse_different(mouse):
    config.save(Config(reactive="off"))
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        field = app.query_one("#reactive", Input)
        field.focus()
        field.value = ""
        await pilot.press(*"red", "enter")
        await settle(app, pilot)
        field.value = "off"
        await pilot.pause()
        app.query_one("#brightness").value = 50
        await pilot.pause()
        mouse.calls.clear()
        await pilot.press("ctrl+s")
        await settle(app, pilot)
        assert ("set_reactive_color", "off") in mouse.calls


async def test_rapid_previews_send_only_the_newest(mouse):
    gated = GatedMouse(mouse)
    app = Rival5App(opener=lambda: gated, status=lambda: device.CONNECTED)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.press("down")  # Logo
        for color in ("#000001", "#000002", "#000003", "#000004"):
            app._set_color(color)
        gated.gate.set()
        await settle(app, pilot)
        sent = [call[1] for call in mouse.calls if call[0] == "set_logo_color"]
        assert sent[-1] == "#000004"
        assert "#000002" not in sent and "#000003" not in sent


async def test_second_preview_only_writes_the_changed_led(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        app._set_color("#111111")
        await settle(app, pilot)
        mouse.calls.clear()
        await pilot.press("down")  # Logo
        app._set_color("#222222")
        await settle(app, pilot)
        assert mouse.calls == [("set_logo_color", "#222222")]


async def test_preview_recovers_after_the_mouse_was_missing(mouse):
    attempts = []

    def opener():
        attempts.append(1)
        if len(attempts) == 1:
            raise device.DeviceError(device.NOT_FOUND)
        return mouse

    app = Rival5App(opener=opener, status=lambda: device.MISSING)
    async with app.run_test(size=(100, 34)) as pilot:
        app._set_color("red")
        await settle(app, pilot)
        assert app._notifications
        app._set_color("blue")
        await settle(app, pilot)
        assert ("set_logo_color", "#0000ff") in mouse.calls


async def test_pick_shortcut_is_only_on_the_lighting_tab(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.press("right", "p")
        assert not isinstance(app.screen, ColorPicker)


def inside(inner, outer):
    return outer.contains_region(inner)


async def test_lighting_tab_fits_a_standard_terminal(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        for selector in ("#rainbow", "#pick-color", "#pick-reactive", "#swatch-white"):
            assert inside(app.query_one(selector).region, app.screen.region)


async def test_picker_fits_a_standard_terminal(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("p")
        await pilot.pause()
        dialog = app.screen.query_one(".color-dialog")
        assert inside(dialog.region, app.screen.region)
        for selector in ("#picker-hint", "#picked", "#use", "#cancel"):
            assert inside(app.screen.query_one(selector).region, dialog.content_region)
