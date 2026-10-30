import pytest
from textual.widgets import Input, OptionList

from rival5 import cli, config, device
from rival5.config import Config
from rival5.tui import ConfirmScreen, Rival5App


def make_app(mouse):
    return Rival5App(opener=lambda: mouse, status=lambda: device.CONNECTED)


async def settle(app, pilot):
    await app.workers.wait_for_complete()
    await pilot.pause()


async def open_tab(app, pilot):
    await pilot.press("left")
    await pilot.pause()
    assert app.query_one("#tabs").active == "profiles-tab"


@pytest.fixture
def fake(mouse, monkeypatch):
    monkeypatch.setattr(device, "open_mouse", lambda: mouse)
    return mouse


def save_profile(name, **values):
    config.save(Config(**values), config.profile_path(name))


def test_round_trip():
    cfg = Config(sensitivity=[800], zones={"all": "orange"}, buttons={"button4": "F13"})
    config.save(cfg, config.profile_path("Játék 1"))
    assert config.list_profiles() == ["Játék 1"]
    assert config.load_profile("Játék 1") == cfg


@pytest.mark.parametrize(
    "name", ["", " ", "../evil", "a/b", "a.b", ".hidden", "-x", "x" * 33, "a\\b"]
)
def test_bad_names_are_refused(name):
    with pytest.raises(ValueError):
        config.profile_path(name)


def test_missing_profile_is_an_error_not_defaults():
    with pytest.raises(ValueError):
        config.load_profile("nope")


def test_active_profile_skips_corrupt_files():
    config.profiles_dir().mkdir(parents=True)
    (config.profiles_dir() / "broken.toml").write_text("not toml [")
    save_profile("good", sensitivity=[800])
    assert config.active_profile(Config(sensitivity=[800])) == "good"
    assert config.active_profile(Config(sensitivity=[900])) is None


def test_send_profile_resets_leds_it_does_not_cover(mouse):
    device.send_profile(mouse, Config(zones={"logo": "red"}), Config())
    assert ("set_logo_color", "#ff0000") in mouse.calls
    assert ("set_wheel_color", config.DEFAULT_LED_COLOR) in mouse.calls


def test_send_profile_keeps_rainbow(mouse):
    device.send_profile(mouse, Config(rainbow=True), Config())
    assert "set_rainbow_effect" in mouse.names()
    assert "set_wheel_color" not in mouse.names()


def test_send_profile_leaves_cpi_alone_when_equal(mouse):
    cfg = Config(sensitivity=[800], zones={"all": "red"})
    device.send_profile(mouse, cfg, Config(sensitivity=[800]))
    assert "set_sensitivity" not in mouse.names()
    assert "save" in mouse.names()


def test_send_profile_sends_colors_even_when_equal(mouse):
    cfg = Config(zones={"all": "red"})
    device.send_profile(mouse, cfg, Config(zones={"all": "red"}))
    assert "set_logo_color" in mouse.names()


def test_normal_lighting_leaves_uncovered_leds_alone(mouse):
    device.send_lighting(mouse, Config(zones={"logo": "red"}))
    assert mouse.names() == ["set_logo_color"]


def test_cli_save_list_load_delete(fake, capsys):
    config.save(Config(sensitivity=[800]))
    assert cli.main(["profile", "save", "work"]) == 0
    config.save(Config(sensitivity=[1600]))
    assert cli.main(["profile", "list"]) == 0
    assert capsys.readouterr().out == "  work\n"
    assert cli.main(["profile", "load", "work"]) == 0
    assert config.load().sensitivity == [800]
    assert fake.names().count("save") == 1
    assert cli.main(["profile", "list"]) == 0
    assert capsys.readouterr().out == "* work\n"
    assert cli.main(["profile", "delete", "work"]) == 0
    assert config.list_profiles() == []


def test_cli_save_needs_force_to_overwrite(capsys):
    save_profile("work")
    assert cli.main(["profile", "save", "work"]) == 1
    assert "--force" in capsys.readouterr().err
    assert cli.main(["profile", "save", "work", "--force"]) == 0


def test_cli_load_no_save_keeps_config_and_flash(fake):
    config.save(Config(sensitivity=[1600]))
    save_profile("work", sensitivity=[800])
    assert cli.main(["--no-save", "profile", "load", "work"]) == 0
    assert config.load().sensitivity == [1600]
    assert "save" not in fake.names()


def test_cli_load_refuses_no_left_click(fake, capsys):
    save_profile("bad", buttons={"button1": "disabled"})
    assert cli.main(["profile", "load", "bad"]) == 1
    assert fake.calls == []


def test_cli_delete_missing_profile_fails():
    assert cli.main(["profile", "delete", "nope"]) == 1


async def test_tab_lists_profiles_and_marks_the_active_one(mouse):
    config.save(Config(sensitivity=[800]))
    save_profile("work", sensitivity=[800])
    save_profile("game", sensitivity=[1600])
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await open_tab(app, pilot)
        rows = app.query_one("#profiles", OptionList)
        prompts = [str(rows.get_option_at_index(i).prompt) for i in range(2)]
        assert prompts == ["  game", "● work"]
        assert app.query_one("#profile-name", Input).value == "game"


async def test_empty_tab_is_usable(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await open_tab(app, pilot)
        await pilot.click("#profile-load")
        await pilot.click("#profile-delete")
        await pilot.pause()
        assert app._notifications
        assert not isinstance(app.screen, ConfirmScreen)


async def test_enter_loads_writes_mouse_and_config(mouse):
    config.save(Config(sensitivity=[800]))
    save_profile("game", sensitivity=[1600], zones={"all": "blue"})
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await open_tab(app, pilot)
        await pilot.press("enter")
        await settle(app, pilot)
        assert config.load().sensitivity == [1600]
        assert ("set_sensitivity", [1600]) in mouse.calls
        assert ("set_logo_color", "#0000ff") in mouse.calls
        assert "save" in mouse.names()
        assert not app.dirty
        assert app.query_one("#cpi", OptionList).option_count == 1


async def test_load_with_unsaved_changes_asks_first(mouse):
    save_profile("game", sensitivity=[1600])
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        app.cfg.sensitivity = [900]
        await open_tab(app, pilot)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("escape")
        await settle(app, pilot)
        assert mouse.calls == []
        assert app.cfg.sensitivity == [900]
        await pilot.press("enter")
        await pilot.pause()
        await pilot.click("#load")
        await settle(app, pilot)
        assert app.cfg.sensitivity == [1600]


async def test_corrupt_profile_shows_an_error(mouse):
    config.profiles_dir().mkdir(parents=True)
    (config.profiles_dir() / "broken.toml").write_text("not toml [")
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await open_tab(app, pilot)
        await pilot.press("enter")
        await settle(app, pilot)
        assert app._notifications
        assert mouse.calls == []


async def test_profile_without_left_click_is_refused(mouse):
    save_profile("bad", buttons={"button1": "disabled"})
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await open_tab(app, pilot)
        await pilot.press("enter")
        await settle(app, pilot)
        assert mouse.calls == []
        assert app.cfg == Config()


async def test_save_current_includes_unsaved_changes_and_skips_the_mouse(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        app.cfg.sensitivity = [900]
        await open_tab(app, pilot)
        app.query_one("#profile-name", Input).value = "new one"
        await pilot.click("#profile-save")
        await settle(app, pilot)
        assert config.load_profile("new one").sensitivity == [900]
        assert mouse.calls == []
        assert app.dirty


async def test_overwrite_and_delete_confirm(mouse):
    save_profile("work", sensitivity=[800])
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await open_tab(app, pilot)
        await pilot.click("#profile-save")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert config.load_profile("work").sensitivity == [800]
        await pilot.click("#profile-save")
        await pilot.pause()
        await pilot.click("#overwrite")
        await pilot.pause()
        assert config.load_profile("work") == Config()
        await pilot.click("#profile-delete")
        await pilot.pause()
        await pilot.click("#delete")
        await pilot.pause()
        assert config.list_profiles() == []


async def test_bad_name_is_refused(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        await open_tab(app, pilot)
        app.query_one("#profile-name", Input).value = "../evil"
        await pilot.click("#profile-save")
        await pilot.pause()
        assert app._notifications
        assert config.list_profiles() == []


async def test_reset_keeps_profiles(mouse):
    save_profile("work")
    app = make_app(mouse)
    async with app.run_test(size=(90, 30)) as pilot:
        app._after_reset_prompt("reset")
        await settle(app, pilot)
        assert config.list_profiles() == ["work"]


async def test_tab_fits_a_standard_terminal(mouse):
    app = make_app(mouse)
    async with app.run_test(size=(80, 24)) as pilot:
        await open_tab(app, pilot)
        for selector in ("#profile-name", "#profile-delete", "#profiles"):
            region = app.query_one(selector).region
            assert app.screen.region.contains_region(region)
            assert region.height > 0
        assert app.query_one("#profile-delete").region.bottom <= 23
