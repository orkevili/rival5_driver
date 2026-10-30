"""A color picker for the terminal: keyboard and mouse, previewed as you move."""

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from . import config

WIDTH, HEIGHT = 34, 10
HINT = "arrows color   , . hue"


def _clamp(fraction):
    return min(max(fraction, 0.0), 1.0)


def _hex(hue, saturation, value):
    return Color.from_hsv(hue, saturation, value).hex.lower()


class Draggable(Widget):
    """Report the position of a click, and of a drag that started here."""

    dragging = False

    def pick(self, x, y):
        raise NotImplementedError

    def on_mouse_down(self, event):
        self.dragging = True
        self.capture_mouse()
        self.pick(event.x, event.y)

    def on_mouse_move(self, event):
        if self.dragging:
            self.pick(event.x, event.y)

    def on_mouse_up(self):
        self.dragging = False
        self.release_mouse()


class ColorField(Draggable):
    """Saturation left to right, brightness top to bottom."""

    hue = reactive(0.0)
    saturation = reactive(0.0)
    value = reactive(0.0)

    def render(self):
        cursor = (
            round(self.saturation * (WIDTH - 1)),
            round((1 - self.value) * (HEIGHT - 1)),
        )
        mark = "#000000" if self.value > 0.5 else "#ffffff"
        lines = []
        for row in range(HEIGHT):
            # Each cell shows two pixels: the top in the foreground of a half
            # block, the bottom in its background.
            top = 1 - row / HEIGHT
            bottom = 1 - (row + 0.5) / HEIGHT
            line = Text(no_wrap=True)
            for column in range(WIDTH):
                saturation = column / (WIDTH - 1)
                upper = _hex(self.hue, saturation, top)
                lower = _hex(self.hue, saturation, bottom)
                if (column, row) == cursor:
                    line.append("┼", f"{mark} on {lower}")
                else:
                    line.append("▀", f"{upper} on {lower}")
            lines.append(line)
        return Text("\n", no_wrap=True).join(lines)

    def pick(self, x, y):
        self.screen.move_to(x / (WIDTH - 1), 1 - y / (HEIGHT - 1))


class HueBar(Draggable):
    hue = reactive(0.0)

    def render(self):
        cursor = round(self.hue * (WIDTH - 1))
        line = Text(no_wrap=True)
        for column in range(WIDTH):
            color = _hex(column / (WIDTH - 1), 1.0, 1.0)
            line.append("┼" if column == cursor else " ", f"#000000 on {color}")
        return line

    def pick(self, x, y):
        self.screen.set_hue(x / (WIDTH - 1))


class ColorPicker(ModalScreen):
    """Return the chosen hex, or None if cancelled.

    on_change is called with each new color, for a live preview.
    """

    AUTO_FOCUS = ""
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "accept", "Use"),
        Binding("left", "move(-1, 0)", show=False),
        Binding("right", "move(1, 0)", show=False),
        Binding("up", "move(0, 1)", show=False),
        Binding("down", "move(0, -1)", show=False),
        # Square brackets need AltGr on some layouts, such as Hungarian.
        Binding("comma,left_square_bracket", "step_hue(-1)", show=False),
        Binding("full_stop,right_square_bracket", "step_hue(1)", show=False),
    ]

    def __init__(self, title, color, on_change):
        super().__init__()
        self.title_text = title
        self.on_change = on_change
        self.hue, self.saturation, self.value = Color.parse(
            config.color_hex(color)
        ).hsv

    @property
    def color(self):
        return _hex(self.hue, self.saturation, self.value)

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog color-dialog"):
            yield Label(self.title_text)
            yield ColorField()
            yield HueBar()
            yield Static("", id="picked")
            yield Label(HINT, id="picker-hint")
            with Horizontal(classes="dialog-buttons"):
                for choice, label in (("cancel", "Esc Cancel"), ("use", "Enter Use")):
                    button = Button(label, id=choice)
                    # Keep Enter and the arrows on the screen's bindings.
                    button.can_focus = False
                    yield button

    def on_mount(self):
        self._show()

    def _show(self):
        field = self.query_one(ColorField)
        field.hue = self.hue
        field.saturation = self.saturation
        field.value = self.value
        self.query_one(HueBar).hue = self.hue
        color = self.color
        self.query_one("#picked", Static).update(
            Text.assemble(("    ", f"on {color}"), f" {color}")
        )

    def _changed(self):
        self._show()
        self.on_change(self.color)

    def move_to(self, saturation, value):
        self.saturation = _clamp(saturation)
        self.value = _clamp(value)
        self._changed()

    def set_hue(self, hue):
        self.hue = _clamp(hue)
        self._changed()

    def action_move(self, across, up):
        self.move_to(
            self.saturation + across / (WIDTH - 1),
            self.value + up / (HEIGHT - 1),
        )

    def action_step_hue(self, direction):
        self.set_hue(self.hue + direction / (WIDTH - 1))

    def action_accept(self):
        self.dismiss(self.color)

    def action_cancel(self):
        self.dismiss(None)

    def on_button_pressed(self, event):
        if event.button.id == "use":
            self.action_accept()
        else:
            self.action_cancel()
