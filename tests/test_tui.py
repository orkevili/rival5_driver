import pytest
from textual.widgets import Input, Select, Static

from rival5 import __version__, config, device
from rival5.config import Config
from rival5.tui import ButtonPicker, ConfirmScreen, Rival5App


def make_app(mouse):
    return Rival5App(opener=lambda: mouse, status=lambda: device.CONNECTED)


async def settle(app, pilot):
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_opens_on_lighting_with_mouse_connected(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)):
        assert app.query_one("#tabs").active == "lighting"
        assert app.focused.id == "zones"
        assert "connected" in str(app.query_one("#status", Static).render())
        assert not app.dirty


async def test_color_previews_live_but_is_not_saved(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        app.query_one("#color", Input).focus()
        await pilot.press(*"red", "enter")
        await settle(app, pilot)
        assert "set_logo_color" in mouse.names()
        assert "save" not in mouse.names()
        assert app.cfg.zones == {"all": "red"}
        assert app.dirty
        assert not config.default_path().exists()


async def test_enter_on_zone_goes_to_color_field(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("enter")
        assert app.focused.id == "color"


async def test_arrow_keys_stay_in_text_fields(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        app.query_one("#color", Input).focus()
        await pilot.press("r", "left", "right")
        assert app.query_one("#tabs").active == "lighting"


async def test_invalid_color_changes_nothing(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        app.query_one("#color", Input).focus()
        await pilot.press(*"nope", "enter")
        await settle(app, pilot)
        assert mouse.calls == []
        assert not app.dirty


async def test_swatch_sets_selected_zone(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.press("down")  # Logo
        await pilot.click("#swatch-lime")
        await settle(app, pilot)
        assert app.cfg.zones == {"logo": "lime"}


async def test_rainbow_button(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.click("#rainbow")
        await settle(app, pilot)
        assert mouse.names() == ["set_rainbow_effect"]
        assert app.cfg.rainbow is True


async def test_save_writes_config_and_mouse(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right")
        assert app.query_one("#tabs").active == "cpi-tab"
        assert app.focused.id == "cpi"
        await pilot.press("plus", "s")
        await settle(app, pilot)
        assert config.load().sensitivity[0] == 500
        assert mouse.names() == ["set_sensitivity", "save"]
        assert not app.dirty


async def test_cpi_changes_wait_for_save(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "minus")
        await settle(app, pilot)
        assert app.cfg.sensitivity[0] == 300
        assert mouse.calls == []


async def test_cpi_limits(mouse):
    config.save(Config(sensitivity=[100]))
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "minus")
        assert app.cfg.sensitivity == [100]
        await pilot.press("d")
        assert app.cfg.sensitivity == [100]
        await pilot.press("a", "a", "a", "a", "a")
        assert len(app.cfg.sensitivity) == 5


async def test_cpi_remove_keeps_cursor_in_range(mouse):
    config.save(Config(sensitivity=[400, 800]))
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "down", "d")
        await pilot.press("plus")
        assert app.cfg.sensitivity == [500]


async def test_bind_with_picker_and_filter(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "right")
        assert app.focused.id == "buttons"
        await pilot.press("down", "down", "down", "enter")
        await pilot.pause()
        assert isinstance(app.screen, ButtonPicker)
        await pilot.press(*"f13", "enter")
        await pilot.pause()
        assert app.cfg.buttons == {"button4": "F13"}
        await pilot.press("s")
        await settle(app, pilot)
        assert config.load().buttons == {"button4": "F13"}
        assert mouse.calls[0] == (
            "set_buttons_mapping",
            {"buttons": {"button4": "F13"}},
        )


async def test_picker_arrow_keys_choose_lower_rows(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "right", "down", "down", "down", "enter")
        await pilot.pause()
        await pilot.press("down", "down", "enter")  # default, button1, button2
        await pilot.pause()
        assert app.cfg.buttons == {"button4": "button2"}


async def test_picker_escape_cancels(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "right", "enter")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.cfg.buttons == {}
        assert not isinstance(app.screen, ButtonPicker)


async def test_picker_shows_keys_with_markup_characters(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "right", "down", "down", "down", "enter")
        await pilot.pause()
        await pilot.press("[", "enter")
        await pilot.pause()
        assert app.cfg.buttons == {"button4": "["}


async def test_picker_refuses_losing_left_click(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "right", "enter")  # button1
        await pilot.pause()
        await pilot.press("a", "enter")
        await pilot.pause()
        assert app.cfg.buttons == {}


async def test_quit_without_changes_exits(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("q")
        await pilot.pause()
        assert not app.is_running or app._exit


@pytest.mark.parametrize("choice", ["cancel", "discard", "save"])
async def test_quit_with_changes_asks(mouse, choice):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "plus", "q")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.click(f"#{choice}")
        await settle(app, pilot)
        if choice == "cancel":
            assert app.dirty and not config.default_path().exists()
        elif choice == "discard":
            assert not config.default_path().exists()
            assert mouse.calls == []
        else:
            assert config.load().sensitivity[0] == 500


async def test_discard_puts_previewed_colors_back(mouse):
    config.save(Config(zones={"all": "blue"}))
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.click("#swatch-red")
        await settle(app, pilot)
        mouse.calls.clear()
        await pilot.press("q")
        await pilot.pause()
        await pilot.click("#discard")
        await settle(app, pilot)
        assert ("set_logo_color", "#0000ff") in mouse.calls


async def test_no_mouse_still_edits_config():
    def missing():
        raise device.DeviceError(device.NOT_FOUND)

    app = Rival5App(opener=missing, status=lambda: device.MISSING)
    async with app.run_test(size=(90, 30)) as pilot:
        assert "not connected" in str(app.query_one("#status", Static).render())
        await pilot.press("right", "plus", "s")
        await settle(app, pilot)
        assert config.load().sensitivity[0] == 500
        messages = [note.message for note in app._notifications]
        assert any("wasn't updated" in message for message in messages)


async def test_polling_select_is_pending(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "right", "right")
        assert app.focused.id == "polling"
        app.query_one("#polling", Select).value = 500
        await pilot.pause()
        assert app.cfg.polling == 500
        assert mouse.calls == []


async def test_factory_reset(mouse):
    config.save(Config(buttons={"button4": "a"}))
    app = make_app(mouse)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.press("right", "right", "right")
        await pilot.click("#reset")
        await pilot.pause()
        await pilot.click("ConfirmScreen #reset")
        await settle(app, pilot)
        assert "reset_settings" in mouse.names()
        assert not config.default_path().exists()
        assert app.cfg == Config()


async def test_broken_config_is_reported(mouse):
    path = config.default_path()
    path.parent.mkdir(parents=True)
    path.write_text("[polling\n")
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)):
        assert any("config.toml" in note.message for note in app._notifications)


def test_list_of_zones_matches_config():
    from rival5.tui import ZONE_LABELS

    assert set(ZONE_LABELS) == set(config.ZONES)


async def test_header_shows_version(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)):
        assert __version__ in str(app.query_one("#title", Static).render())


async def test_css_color_name_previews_as_hex(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        app.query_one("#color", Input).focus()
        await pilot.press(*"orange", "enter")
        await settle(app, pilot)
        assert ("set_logo_color", "#ff4500") in mouse.calls
        assert app.cfg.zones == {"all": "orange"}


async def type_reactive(app, pilot, text):
    field = app.query_one("#reactive", Input)
    field.focus()
    field.value = ""
    await pilot.press(*text)


async def test_reactive_typed_then_tab_then_s_saves(mouse):
    config.save(Config(reactive="white"))
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await type_reactive(app, pilot, "off")
        await pilot.press("tab", "s")
        await settle(app, pilot)
        assert config.load().reactive == "off"
        assert ("set_reactive_color", "off") in mouse.calls


async def test_half_typed_reactive_is_quiet_and_keeps_the_old_value(mouse):
    config.save(Config(reactive="white"))
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await type_reactive(app, pilot, "of")
        assert app.cfg.reactive == "white"
        assert not app._notifications


async def test_invalid_reactive_reports_when_leaving_the_field(mouse):
    config.save(Config(reactive="white"))
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await type_reactive(app, pilot, "nope")
        await pilot.press("tab")
        assert app.cfg.reactive == "white"
        assert app._notifications


async def test_ctrl_s_saves_from_inside_a_field(mouse):
    config.save(Config(reactive="white"))
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await type_reactive(app, pilot, "off")
        await pilot.press("ctrl+s")
        await settle(app, pilot)
        assert config.load().reactive == "off"
        assert app.query_one("#reactive", Input).value == "off"


async def test_ctrl_s_does_nothing_behind_a_dialog(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right")
        await pilot.press("plus", "q")
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("ctrl+s")
        await settle(app, pilot)
        assert not config.default_path().exists()


class FakeWatch:
    def __init__(self, callback):
        self.callback = callback
        self.closed = False

    def close(self):
        self.closed = True


def make_watched_app(mouse, watches):
    def watcher(callback):
        watches.append(FakeWatch(callback))
        return watches[-1]

    return Rival5App(
        opener=lambda: mouse, status=lambda: device.CONNECTED, watcher=watcher
    )


def highlighted_button(app):
    buttons = app.query_one("#buttons")
    return buttons.get_option_at_index(buttons.highlighted).id


async def test_mouse_press_selects_its_button(mouse):
    watches = []
    app = make_watched_app(mouse, watches)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "right")
        watches[-1].callback("button4")
        await pilot.pause()
        assert highlighted_button(app) == "button4"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ButtonPicker)
        assert app.screen.button == "button4"


@pytest.mark.parametrize("action", ["F13", "f13"])
async def test_mouse_press_finds_a_rebound_button(mouse, action):
    config.save(Config(buttons={"button5": action}))
    watches = []
    app = make_watched_app(mouse, watches)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "right")
        watches[-1].callback("F13")
        await pilot.pause()
        assert highlighted_button(app) == "button5"


async def test_mouse_press_finds_an_alias(mouse):
    config.save(Config(buttons={"button5": "vol+"}))
    watches = []
    app = make_watched_app(mouse, watches)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "right")
        watches[-1].callback("VolumeUp")
        await pilot.pause()
        assert highlighted_button(app) == "button5"


async def test_mouse_press_uses_saved_bindings(mouse):
    watches = []
    app = make_watched_app(mouse, watches)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "right")
        app._bind("button4", "F13")
        watches[-1].callback("F13")
        await pilot.pause()
        assert highlighted_button(app) == "button1"
        watches[-1].callback("button4")
        await pilot.pause()
        assert highlighted_button(app) == "button4"


async def test_mouse_press_ignored_behind_a_dialog(mouse):
    watches = []
    app = make_watched_app(mouse, watches)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "right", "enter")
        await pilot.pause()
        watches[-1].callback("button4")
        await pilot.pause()
        assert highlighted_button(app) == "button1"


async def test_watch_only_runs_on_the_buttons_tab(mouse):
    watches = []
    app = make_watched_app(mouse, watches)
    async with app.run_test(size=(90, 30)) as pilot:
        assert watches == []
        await pilot.press("right", "right")
        await pilot.pause()
        assert app.watch is watches[-1]
        assert "Press a mouse button" in str(app.query_one("#buttons-hint").render())
        await pilot.press("right")
        await pilot.pause()
        assert watches[-1].closed
        assert app.watch is None


async def test_watch_closes_on_exit(mouse):
    watches = []
    app = make_watched_app(mouse, watches)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "right")
        await pilot.pause()
    assert watches[-1].closed


async def test_watch_restarts_after_a_replug(mouse):
    watches = []
    app = make_watched_app(mouse, watches)
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "right")
        await pilot.pause()
        first = watches[-1]
        first.closed = True
        app.refresh_status()
        assert app.watch is watches[-1]
        assert app.watch is not first


async def test_buttons_tab_works_without_a_watch(mouse):
    def unavailable(callback):
        raise OSError("no access")

    app = Rival5App(
        opener=lambda: mouse, status=lambda: device.CONNECTED, watcher=unavailable
    )
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("right", "right")
        await pilot.pause()
        assert app.watch is None
        hint = str(app.query_one("#buttons-hint").render())
        assert "Press a mouse button" not in hint
        assert app.focused.id == "buttons"
