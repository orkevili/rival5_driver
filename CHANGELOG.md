# Changelog

## 0.5.0

- Pressing a button on the mouse selects it on the Buttons tab, so you can find it without knowing its name. This needs no new permissions, and the mouse is only read while that tab is open.

## 0.4.0

- Add profiles: save, load and delete whole configurations from the new Profiles tab or with `rival5 profile`.
- Fix the wheel keeping its old color when colors are sent right after a save.

## 0.3.0

- Add a color picker for zones and the reactive color, with mouse and keyboard control and a live preview.
- Preview the reactive color on Enter. Discarding puts the saved one back.
- Fast previews no longer pile up or finish out of order: only the newest is sent, and only for LEDs that changed.

## 0.2.0

- Show the version in the TUI header and with `rival5 --version`.
- Accept CSS color names such as `orange`, plus `rgb()` and `hsl()`.
- Add orange and pink swatches, with both colors adjusted for the LEDs.
- Fix the Reactive field: a value now counts as soon as it is valid, without pressing Enter. Previously, typing `off` and saving said "Nothing to save".
- Add `Ctrl+S`, which saves from inside text fields too.

## 0.1.0

- First version: TUI and commands for colors, CPI, polling rate, brightness and button bindings.
