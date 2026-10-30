import pytest
from textual.widgets import Input, Select, Static

from rival5 import config, device
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
        assert ("set_logo_color", "blue") in mouse.calls


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
