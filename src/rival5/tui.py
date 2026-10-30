"""The terminal UI. Only colors reach the mouse before you press save."""

import copy
import threading
from dataclasses import replace

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
    OptionList,
    Select,
    Static,
    TabbedContent,
    TabPane,
)
from textual.widgets.option_list import Option

from . import __version__, config, device
from .colorpicker import ColorPicker

TABS = ["lighting", "cpi", "buttons", "device", "profiles"]
TAB_LABELS = {
    "lighting": "Lighting",
    "cpi": "CPI",
    "buttons": "Buttons",
    "device": "Device",
    "profiles": "Profiles",
}
TAB_FIELDS = {
    "lighting": ("zones", "rainbow", "brightness", "reactive", "startup"),
    "cpi": ("sensitivity",),
    "buttons": ("buttons",),
    "device": ("polling",),
    "profiles": (),
}
TAB_FOCUS = {
    "lighting": "#zones",
    "cpi": "#cpi",
    "buttons": "#buttons",
    "device": "#polling",
    "profiles": "#profiles",
}
ZONE_LABELS = {
    "all": "All",
    "logo": "Logo",
    "wheel": "Wheel",
    "left": "Left strip",
    "right": "Right strip",
    "z2": "Left top",
    "z4": "Left upper middle",
    "z6": "Left lower middle",
    "z8": "Left bottom",
    "z3": "Right top",
    "z5": "Right upper middle",
    "z7": "Right lower middle",
    "z9": "Right bottom",
}
MOUSE_ERRORS = (device.DeviceError, OSError, ValueError)
HINT = "←/→ tabs   ↑/↓ move   tab next field   enter edit   ctrl+s save"
SWATCHES = [
    "red",
    "orange",
    "yellow",
    "lime",
    "aqua",
    "blue",
    "fuchsia",
    "pink",
    "white",
]
ACTION_GROUPS = [
    ("mouse", config.MOUSE_ACTIONS),
    ("special", config.SPECIAL_ACTIONS),
    ("media", config.MEDIA_KEYS),
    ("key", config.KEYBOARD_KEYS),
]


class ConfirmScreen(ModalScreen):
    """Ask a question and return the id of the button pressed."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, question, choices):
        super().__init__()
        self.question = question
        self.choices = choices

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.question)
            with Horizontal(classes="dialog-buttons"):
                for choice, label in self.choices:
                    yield Button(label, id=choice)

    def on_button_pressed(self, event):
        self.dismiss(event.button.id)

    def action_cancel(self):
        self.dismiss(None)


class ButtonPicker(ModalScreen):
    """Pick an action for a button from a type-to-filter list."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, button):
        super().__init__()
        self.button = button

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog picker"):
            yield Label(f"Bind {self.button}")
            yield Input(placeholder="Type to filter", id="filter")
            yield OptionList(id="actions")

    def on_mount(self):
        self._fill("")

    def _fill(self, text):
        actions = self.query_one("#actions", OptionList)
        actions.clear_options()
        needle = text.lower()
        rows = [("default", "")]
        rows += [
            (action, kind)
            for kind, group in ACTION_GROUPS
            for action in group
        ]
        for action, kind in rows:
            if needle in action.lower():
                prompt = Text.assemble(f"{action:<16}", (kind, "dim"))
                actions.add_option(Option(prompt, id=f"action-{action}"))
        if actions.option_count:
            actions.highlighted = 0

    @on(Input.Changed, "#filter")
    def _filter(self, event):
        self._fill(event.value)

    def on_key(self, event):
        actions = self.query_one("#actions", OptionList)
        if event.key == "down":
            actions.action_cursor_down()
            event.stop()
        elif event.key == "up":
            actions.action_cursor_up()
            event.stop()

    @on(Input.Submitted, "#filter")
    def _submit(self):
        actions = self.query_one("#actions", OptionList)
        if actions.highlighted is not None:
            self._choose(actions.get_option_at_index(actions.highlighted))

    @on(OptionList.OptionSelected, "#actions")
    def _selected(self, event):
        self._choose(event.option)

    def _choose(self, option):
        self.dismiss(option.id.removeprefix("action-"))

    def action_cancel(self):
        self.dismiss(None)


class CpiList(OptionList):
    BINDINGS = [
        Binding("plus,equals_sign", "step(1)", "+100"),
        Binding("minus", "step(-1)", "-100"),
        Binding("a", "add", "Add"),
        Binding("d,delete", "remove", "Remove"),
    ]

    def action_step(self, direction):
        self.app.cpi_step(direction)

    def action_add(self):
        self.app.cpi_add()

    def action_remove(self):
        self.app.cpi_remove()


class Rival5App(App):
    CSS_PATH = "tui.tcss"
    TITLE = "Rival 5"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("left", "tab(-1)", "Prev tab", show=False),
        Binding("right", "tab(1)", "Next tab", show=False),
        Binding("p", "pick", "Pick color"),
        Binding("s", "save", "Save"),
        Binding("ctrl+s", "save", "Save", show=False, priority=True),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, opener=None, status=None):
        super().__init__()
        self.opener = opener or device.open_mouse
        self.read_status = status or device.status
        self.saved = None
        self.cfg = None
        self.load_error = None
        self.io_lock = threading.Lock()
        self.preview_lock = threading.Lock()
        self.next_preview = None
        self.previewing = False
        self.last_leds = None
        try:
            self.saved = config.load()
        except ValueError as error:
            self.load_error = str(error)
            self.saved = config.Config()
        self.cfg = copy.deepcopy(self.saved)
        self.mouse_reactive = self.saved.reactive

    @property
    def dirty(self):
        return self.cfg != self.saved

    def compose(self) -> ComposeResult:
        with Horizontal(id="header"):
            yield Static(f"Rival 5 v{__version__}", id="title")
            yield Static("", id="status")
        with TabbedContent(initial="lighting", id="tabs"):
            with TabPane("Lighting", id="lighting"):
                with Horizontal():
                    yield OptionList(id="zones")
                    with Vertical(id="lighting-controls"):
                        with Horizontal(id="color-row"):
                            yield Input(placeholder="#00aaff or red", id="color")
                            yield Button("Pick…", id="pick-color", classes="pick")
                            yield Button("Rainbow", id="rainbow")
                        with Horizontal(id="swatches"):
                            for name in SWATCHES:
                                swatch = Button("", id=f"swatch-{name}", classes="swatch")
                                swatch.styles.background = config.color_hex(name)
                                yield swatch
                        with Grid(id="lighting-grid"):
                            yield Label("Brightness")
                            yield Select(
                                [(f"{v}%", v) for v in config.BRIGHTNESS_LEVELS],
                                value=self.cfg.brightness,
                                allow_blank=False,
                                id="brightness",
                            )
                            yield Label("Reactive")
                            with Horizontal(id="reactive-row"):
                                yield Input(
                                    value=self.cfg.reactive,
                                    placeholder="off or a color",
                                    id="reactive",
                                )
                                yield Button(
                                    "Pick…", id="pick-reactive", classes="pick"
                                )
                            yield Label("On startup")
                            yield Select(
                                [(mode, mode) for mode in config.STARTUP_MODES],
                                value=self.cfg.startup,
                                allow_blank=False,
                                id="startup",
                            )
            with TabPane("CPI", id="cpi-tab"):
                with Vertical():
                    yield Label("Presets, cycled by the CPI button")
                    yield CpiList(id="cpi")
                    with Horizontal(classes="row"):
                        yield Button("-100", id="cpi-down")
                        yield Button("+100", id="cpi-up")
                        yield Button("Add", id="cpi-add")
                        yield Button("Remove", id="cpi-remove")
            with TabPane("Buttons", id="buttons-tab"):
                with Vertical():
                    yield Label("Enter changes the selected button")
                    yield OptionList(id="buttons")
            with TabPane("Device", id="device-tab"):
                with Vertical():
                    with Grid(id="device-grid"):
                        yield Label("Polling rate")
                        yield Select(
                            [(f"{v} Hz", v) for v in config.POLLING_RATES],
                            value=self.cfg.polling,
                            allow_blank=False,
                            id="polling",
                        )
                    with Horizontal(classes="row"):
                        yield Button("Send all to mouse", id="apply-all")
                        yield Button("Factory reset", id="reset", variant="error")
            with TabPane("Profiles", id="profiles-tab"):
                with Vertical():
                    yield Label("Saved configurations. Enter loads the selected one")
                    yield OptionList(id="profiles")
                    with Horizontal(id="profile-row", classes="row"):
                        yield Input(placeholder="Profile name", id="profile-name")
                        yield Button("Load", id="profile-load")
                        yield Button("Save current", id="profile-save")
                        yield Button("Delete", id="profile-delete")
        yield Static("", id="pending")
        yield Footer()

    def on_mount(self):
        self.refresh_all()
        self.refresh_status()
        self.set_interval(2, self.refresh_status)
        self.query_one("#zones", OptionList).focus()
        if self.load_error:
            self.notify(self.load_error, severity="error", timeout=15)

    def refresh_status(self):
        state = self.read_status()
        mark = "●" if state == device.CONNECTED else "○"
        status = self.query_one("#status", Static)
        status.update(f"{mark} {state}")
        status.set_class(state == device.CONNECTED, "ok")

    def refresh_all(self):
        self.refresh_zones()
        self.refresh_cpi()
        self.refresh_buttons()
        self.refresh_profiles()
        self.refresh_pending()
        self.query_one("#brightness", Select).value = self.cfg.brightness
        self.query_one("#startup", Select).value = self.cfg.startup
        self.query_one("#polling", Select).value = self.cfg.polling
        self.query_one("#reactive", Input).value = self.cfg.reactive

    def refresh_pending(self):
        tabs = self.query_one("#tabs", TabbedContent)
        for name in TABS:
            changed = any(
                getattr(self.cfg, field) != getattr(self.saved, field)
                for field in TAB_FIELDS[name]
            )
            pane = "lighting" if name == "lighting" else f"{name}-tab"
            marker = " ●" if changed else ""
            tabs.get_tab(pane).label = TAB_LABELS[name] + marker
        pending = self.query_one("#pending", Static)
        pending.update("Unsaved changes: press s or ctrl+s to save" if self.dirty else HINT)
        pending.set_class(self.dirty, "unsaved")

    def _zone_color(self, zone):
        if zone in self.cfg.zones:
            return self.cfg.zones[zone]
        if zone in config.LEDS:
            return config.resolve_zones(self.cfg.zones).get(zone)
        return None

    def _zone_prompt(self, zone):
        color = self._zone_color(zone)
        style = f"on {config.color_hex(color)}" if color else ""
        # Non-breaking, or an empty swatch loses its width and the rows misalign.
        return Text.assemble(("\u00a0\u00a0", style), f" {ZONE_LABELS[zone]}")

    def refresh_zones(self):
        zones = self.query_one("#zones", OptionList)
        if zones.option_count:
            for zone in ZONE_LABELS:
                zones.replace_option_prompt(zone, self._zone_prompt(zone))
        else:
            zones.add_options(
                [Option(self._zone_prompt(zone), id=zone) for zone in ZONE_LABELS]
            )
            zones.highlighted = 0

    def _fill(self, widget, options):
        """Replace a list's rows, keeping the cursor where it was."""
        position = widget.highlighted or 0
        widget.clear_options()
        widget.add_options(options)
        if options:
            widget.highlighted = min(position, widget.option_count - 1)

    def refresh_cpi(self):
        self._fill(
            self.query_one("#cpi", OptionList),
            [Option(Text(f"{cpi} CPI")) for cpi in self.cfg.sensitivity],
        )

    def refresh_buttons(self):
        rows = []
        for button, default in config.BUTTON_DEFAULTS.items():
            action = self.cfg.buttons.get(button, default)
            changed = self.cfg.buttons.get(button) != self.saved.buttons.get(button)
            marker = "●" if changed else " "
            rows.append(Option(Text(f"{marker} {button:<12}{action}"), id=button))
        self._fill(self.query_one("#buttons", OptionList), rows)

    def refresh_profiles(self):
        active = config.active_profile(self.saved)
        rows = []
        for name in config.list_profiles():
            marker = "●" if name == active else " "
            rows.append(Option(Text(f"{marker} {name}"), id=name))
        self._fill(self.query_one("#profiles", OptionList), rows)

    # Actions

    def action_tab(self, offset):
        tabs = self.query_one("#tabs", TabbedContent)
        panes = ["lighting", "cpi-tab", "buttons-tab", "device-tab", "profiles-tab"]
        index = panes.index(tabs.active)
        tabs.active = panes[(index + offset) % len(panes)]

    @on(TabbedContent.TabActivated, "#tabs")
    def _focus_tab(self, event):
        name = event.pane.id.removesuffix("-tab")
        if name == "profiles":
            self.refresh_profiles()
        self.query_one(TAB_FOCUS[name]).focus()

    def check_action(self, action, parameters):
        if action == "pick":
            return self.query_one("#tabs", TabbedContent).active == "lighting"
        return True

    def action_save(self):
        # Ctrl+S is a priority binding, so it also fires behind a dialog.
        if isinstance(self.screen, ModalScreen):
            return
        if not self.dirty:
            self.notify("Nothing to save")
            return
        self._save()

    def _save(self, then_exit=False, send=device.apply, success="Saved to the mouse"):
        try:
            config.validate(self.cfg)
        except ValueError as error:
            self.notify(str(error), severity="error")
            return
        # A previewed reactive color may differ from what was last saved.
        previous = replace(self.saved, reactive=self.mouse_reactive)
        cfg = copy.deepcopy(self.cfg)
        config.save(cfg)
        self.saved = copy.deepcopy(cfg)
        self.mouse_reactive = cfg.reactive
        self.refresh_buttons()
        self.refresh_profiles()
        self.refresh_pending()
        self._with_mouse(
            lambda mouse: send(mouse, cfg, previous),
            success=success,
            failure="Saved to config, but the mouse wasn't updated",
            then_exit=then_exit,
        )

    async def action_quit(self):
        if not self.dirty:
            self.exit()
            return
        self.push_screen(
            ConfirmScreen(
                "You have unsaved changes.",
                [("save", "Save"), ("discard", "Discard"), ("cancel", "Cancel")],
            ),
            self._after_quit_prompt,
        )

    def _after_quit_prompt(self, choice):
        if choice == "save":
            self._save(then_exit=True)
        elif choice == "discard":
            self._discard()

    def _discard(self):
        changed = (
            self.cfg.zones != self.saved.zones
            or self.cfg.rainbow != self.saved.rainbow
            or self.mouse_reactive != self.saved.reactive
        )
        if not changed:
            self.exit()
            return
        # Colors were previewed live, so put the saved ones back.
        saved = copy.deepcopy(self.saved)

        def restore(mouse):
            device.send_lighting(mouse, saved)
            device.send_reactive(mouse, saved)

        self._with_mouse(restore, then_exit=True)

    def _with_mouse(self, job, success=None, failure=None, then_exit=False):
        """Run job in a thread: writes pause between commands."""

        def run():
            error = None
            with self.io_lock:
                self.last_leds = None
                try:
                    with self.opener() as mouse:
                        job(mouse)
                except MOUSE_ERRORS as caught:
                    error = str(caught)
            if error:
                text = f"{failure}: {error}" if failure else error
                self.call_from_thread(self.notify, text, severity="error")
            elif success:
                self.call_from_thread(self.notify, success)
            if then_exit:
                self.call_from_thread(self.exit)

        self.run_worker(run, thread=True, exit_on_error=False)

    def _preview(self):
        self.refresh_zones()
        self.refresh_pending()
        with self.preview_lock:
            self.next_preview = copy.deepcopy(self.cfg)
            if self.previewing:
                return
            self.previewing = True
        self.run_worker(self._send_previews, thread=True, exit_on_error=False)

    def _take_preview(self):
        with self.preview_lock:
            cfg, self.next_preview = self.next_preview, None
            self.previewing = cfg is not None
        return cfg

    def _send_previews(self):
        """Latest wins: a color replaced while waiting is never sent."""
        try:
            with self.io_lock, self.opener() as mouse:
                while cfg := self._take_preview():
                    self.last_leds = device.send_lighting(mouse, cfg, self.last_leds)
                    if cfg.reactive != self.mouse_reactive:
                        device.send_reactive(mouse, cfg)
                        self.mouse_reactive = cfg.reactive
        except MOUSE_ERRORS as error:
            with self.preview_lock:
                self.next_preview = None
                self.previewing = False
            self.last_leds = None
            self.call_from_thread(self.notify, str(error), severity="error")

    # Lighting

    def _selected_zone(self):
        zones = self.query_one("#zones", OptionList)
        return zones.get_option_at_index(zones.highlighted).id

    def _set_color(self, color):
        try:
            config.set_zone(self.cfg, self._selected_zone(), color)
        except ValueError as error:
            self.notify(str(error), severity="error")
            return
        self.query_one("#color", Input).value = color
        self._preview()

    def action_pick(self):
        zone = self._selected_zone()
        before = copy.deepcopy(self.cfg)
        field = self.query_one("#color", Input)
        typed = field.value

        def finished(color):
            if color is None:
                self.cfg = before
                field.value = typed
                self._preview()

        self.push_screen(
            ColorPicker(
                f"Color for {ZONE_LABELS[zone]}",
                self._zone_color(zone) or "red",
                self._set_color,
            ),
            finished,
        )

    def _pick_reactive(self):
        field = self.query_one("#reactive", Input)
        before = self.cfg.reactive
        start = "white" if before.lower() in config.REACTIVE_OFF else before

        def change(color):
            field.value = color
            self._commit_reactive(color, report=False)
            self._preview()

        def finished(color):
            if color is None:
                change(before)

        self.push_screen(ColorPicker("Reactive color", start, change), finished)

    @on(OptionList.OptionHighlighted, "#zones")
    def _zone_highlighted(self, event):
        color = self._zone_color(event.option.id)
        self.query_one("#color", Input).value = color or ""

    @on(OptionList.OptionSelected, "#zones")
    def _zone_selected(self):
        self.query_one("#color", Input).focus()

    @on(Input.Submitted, "#color")
    def _color_submitted(self, event):
        self._set_color(event.value.strip())

    def _commit_reactive(self, value, report):
        value = value.strip()
        try:
            config.check_reactive(value)
        except ValueError as error:
            if report:
                self.notify(str(error), severity="error")
            return False
        self.cfg.reactive = value
        self.refresh_pending()
        return True

    @on(Input.Changed, "#reactive")
    def _reactive_changed(self, event):
        # Half-typed values are normal here, so stay quiet about them.
        self._commit_reactive(event.value, report=False)

    @on(Input.Blurred, "#reactive")
    def _reactive_left(self, event):
        self._commit_reactive(event.value, report=True)

    @on(Input.Submitted, "#reactive")
    def _reactive_submitted(self, event):
        if self._commit_reactive(event.value, report=True):
            self._preview()

    @on(Select.Changed, "#brightness")
    def _brightness_changed(self, event):
        self.cfg.brightness = event.value
        self.refresh_pending()

    @on(Select.Changed, "#startup")
    def _startup_changed(self, event):
        self.cfg.startup = event.value
        self.refresh_pending()

    @on(Select.Changed, "#polling")
    def _polling_changed(self, event):
        self.cfg.polling = event.value
        self.refresh_pending()

    # CPI

    def _cpi_index(self):
        return self.query_one("#cpi", OptionList).highlighted or 0

    def _cpi_changed(self):
        self.refresh_cpi()
        self.refresh_pending()

    def cpi_step(self, direction):
        index = self._cpi_index()
        value = self.cfg.sensitivity[index] + direction * config.CPI_STEP
        if config.MIN_CPI <= value <= config.MAX_CPI:
            self.cfg.sensitivity[index] = value
            self._cpi_changed()

    def cpi_add(self):
        presets = self.cfg.sensitivity
        if len(presets) >= config.MAX_PRESETS:
            self.notify(f"The mouse holds {config.MAX_PRESETS} presets", severity="warning")
            return
        presets.append(min(presets[-1] + 400, config.MAX_CPI))
        self._cpi_changed()

    def cpi_remove(self):
        presets = self.cfg.sensitivity
        if len(presets) == 1:
            self.notify("The mouse needs at least one preset", severity="warning")
            return
        presets.pop(self._cpi_index())
        self._cpi_changed()

    # Buttons

    @on(OptionList.OptionSelected, "#buttons")
    def _button_selected(self, event):
        button = event.option.id
        self.push_screen(
            ButtonPicker(button), lambda action: self._bind(button, action)
        )

    def _bind(self, button, action):
        if action is None:
            return
        candidate = copy.deepcopy(self.cfg)
        config.bind(candidate, button, action)
        if not config.has_left_click(candidate.buttons):
            self.notify(
                "That leaves no left click. Bind another button to button1 first.",
                severity="error",
            )
            return
        self.cfg = candidate
        self.refresh_buttons()
        self.refresh_pending()

    # Profiles

    def _selected_profile(self):
        profiles = self.query_one("#profiles", OptionList)
        if profiles.highlighted is None:
            self.notify("Save a profile first", severity="warning")
            return None
        return profiles.get_option_at_index(profiles.highlighted).id

    @on(OptionList.OptionHighlighted, "#profiles")
    def _profile_highlighted(self, event):
        self.query_one("#profile-name", Input).value = event.option.id

    @on(OptionList.OptionSelected, "#profiles")
    def _profile_selected(self, event):
        self._ask_load_profile(event.option.id)

    def _ask_load_profile(self, name):
        if not self.dirty:
            self._load_profile(name)
            return
        self.push_screen(
            ConfirmScreen(
                f"Load {name} and lose your unsaved changes?",
                [("load", "Load"), ("cancel", "Cancel")],
            ),
            lambda choice: choice == "load" and self._load_profile(name),
        )

    def _load_profile(self, name):
        try:
            cfg = config.load_profile(name)
            config.validate(cfg)
        except ValueError as error:
            self.notify(str(error), severity="error")
            return
        self.cfg = cfg
        self.refresh_all()
        self._save(send=device.send_profile, success=f"Loaded {name}")

    def _ask_save_profile(self):
        name = self.query_one("#profile-name", Input).value.strip()
        try:
            path = config.profile_path(name)
            config.validate(self.cfg)
        except ValueError as error:
            self.notify(str(error), severity="error")
            return
        if not path.exists():
            self._save_profile(name)
            return
        self.push_screen(
            ConfirmScreen(
                f"Overwrite {name}?",
                [("overwrite", "Overwrite"), ("cancel", "Cancel")],
            ),
            lambda choice: choice == "overwrite" and self._save_profile(name),
        )

    def _save_profile(self, name):
        config.save(self.cfg, config.profile_path(name))
        self.refresh_profiles()
        self.notify(f"Saved {name}")

    def _ask_delete_profile(self):
        name = self._selected_profile()
        if name is None:
            return
        self.push_screen(
            ConfirmScreen(
                f"Delete {name}?", [("delete", "Delete"), ("cancel", "Cancel")]
            ),
            lambda choice: choice == "delete" and self._delete_profile(name),
        )

    def _delete_profile(self, name):
        config.delete_profile(name)
        self.refresh_profiles()

    # Button presses

    def on_button_pressed(self, event):
        match event.button.id:
            case "cpi-up":
                self.cpi_step(1)
            case "cpi-down":
                self.cpi_step(-1)
            case "cpi-add":
                self.cpi_add()
            case "cpi-remove":
                self.cpi_remove()
            case "pick-color":
                self.action_pick()
            case "pick-reactive":
                self._pick_reactive()
            case "rainbow":
                self.cfg.rainbow = True
                self._preview()
            case "apply-all":
                self._apply_all()
            case "profile-load":
                if name := self._selected_profile():
                    self._ask_load_profile(name)
            case "profile-save":
                self._ask_save_profile()
            case "profile-delete":
                self._ask_delete_profile()
            case "reset":
                self.push_screen(
                    ConfirmScreen(
                        "Reset the mouse to factory defaults and clear the config?",
                        [("reset", "Reset"), ("cancel", "Cancel")],
                    ),
                    self._after_reset_prompt,
                )
            case name if name and name.startswith("swatch-"):
                self._set_color(name.removeprefix("swatch-"))

    def _apply_all(self):
        cfg = copy.deepcopy(self.saved)
        self._with_mouse(
            lambda mouse: device.apply(mouse, cfg), success="Sent to the mouse"
        )

    def _after_reset_prompt(self, choice):
        if choice != "reset":
            return
        config.default_path().unlink(missing_ok=True)
        self.saved = config.Config()
        self.cfg = config.Config()
        self.mouse_reactive = self.saved.reactive
        self.refresh_all()
        self._with_mouse(device.reset, success="Reset to factory defaults")

