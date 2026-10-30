# rival5_driver

Configure a SteelSeries Rival 5 on Linux from a terminal UI: LED colors, CPI, polling rate and button bindings. SteelSeries GG isn't available on Linux, so this replaces it for those settings.

It's a userspace tool built on [rivalcfg](https://github.com/flozz/rivalcfg), which handles the USB protocol. No kernel module is involved. It adds what rivalcfg leaves open:

- a TUI and a config file that remembers your settings, since the mouse can't be read back
- bindings that add up, because rivalcfg resets every button you don't name
- colors that return after a replug, because the mouse doesn't store them
- LED groups such as `all`, `left` and `right`

Macros aren't supported. Onboard macros on this model are undocumented.

## Install

```sh
./install.sh
```

This installs the `rival5` command for your user (make sure `~/.local/bin` is on your `PATH`), a udev rule that needs `sudo`, and a systemd user service. Then replug the mouse.

The udev rule covers this mouse only and gives access to the logged-in user. You don't need rivalcfg's own `--update-udev`, and its `udev rules are not installed` warning doesn't apply to `rival5`.

## Usage

Run `rival5` to open the TUI.

| Key | Action |
| --- | --- |
| `←` `→` | Switch tab |
| `↑` `↓` | Move in a list |
| `Tab` | Next field |
| `Enter` | Edit the selected item |
| `p` | On the Lighting tab: pick a color for the selected zone |
| `+` `-` `a` `d` | On the CPI tab: step, add, remove |
| Any mouse button | On the Buttons tab: select that button |
| `s` | Save to the config and the mouse |
| `Ctrl+S` | Save, also from inside a text field |
| `q` | Quit |

Colors can be hex (`#00aaff`, `0af`), CSS names (`orange`, `hotpink`), `rgb(0,170,255)` or `hsl(200,100%,50%)`. LEDs don't match a screen exactly, so a color may look different on the mouse. `orange` and `pink` are adjusted for the LEDs; a hex value is always sent as written.

In the color picker, use the mouse or the arrow keys, change the hue with `,` and `.`, then press `Enter` to use the color or `Esc` to go back. The `Pick…` button next to Reactive opens it for the reactive color. Screens and LEDs differ, so pale and mixed colors look paler on the mouse than in the picker.

Colors change on the mouse as you pick them, as a preview. Pressing `Enter` on a reactive color also sends it, and it shows on the next click. Everything else waits for `s`, and tabs with unsaved changes show `●`. If you quit and discard, the saved colors and reactive color are put back.

On the Buttons tab, pressing a button on the mouse selects its row, so `Enter` edits it straight away. The mouse is only read while this tab is open, and nothing is stored.

The same settings are available as commands:

```sh
rival5 color all '#00aaff'        # zones: all left right logo wheel z2-z9
rival5 color wheel orange
rival5 rainbow
rival5 cpi 400 800 1600           # 1-5 presets, 100-18000
rival5 poll 1000                  # 125 250 500 1000
rival5 brightness 75              # 0 25 50 75 100
rival5 bind button4=F13 button5=PlayPause
rival5 unbind button4             # or: unbind --all
rival5 apply                      # send the whole config, after editing it by hand
rival5 show                       # print the config
rival5 reset                      # factory defaults, clears the config
rival5 --version                  # print the version
```

To try a change without keeping it, add `--no-save` before the command. It leaves the config and onboard memory alone, so a replug undoes it:

```sh
rival5 --no-save bind button4=a
```

The config is `~/.config/rival5/config.toml`. See [config.example.toml](config.example.toml) for the format. The TUI and commands rewrite this file, so comments you add aren't kept.

## Profiles

A profile is a saved copy of all your settings. Use the Profiles tab, or:

```sh
rival5 profile save gaming        # add --force to overwrite
rival5 profile load gaming        # switch to it
rival5 profile list               # * marks the one in use
rival5 profile delete gaming
```

Profiles are files in `~/.config/rival5/profiles/`, because the mouse only holds one configuration. Loading one writes it to the mouse and makes it your config, so it survives a replug. A factory reset leaves profiles alone.

Saving a profile includes changes you haven't saved yet, and doesn't change the mouse. LEDs a profile doesn't set return to the mouse's default color when it loads.

## Bindings

A button can be bound to:

- a mouse button, `button1` to `button6`
- `dpi`, `disabled`, `scrollup`, `scrolldown`
- a media key: `Mute`, `Next`, `PlayPause`, `Previous`, `VolumeUp`, `VolumeDown`
- a keyboard key, such as `a`, `F13`, `Enter` or `semicolon`

`rival5` refuses a change that leaves no button sending left click. Use `--force` with `bind`, `unbind` or `apply` to override this.

### Button map

<!-- Fill in from `libinput debug-events` on the real mouse. -->

Not yet confirmed on the hardware, apart from the defaults in the device profile.

| Name | Physical button |
| --- | --- |
| `button1`-`button3` | Left, right, middle |
| `button4`-`button8` | Not confirmed yet |
| `button9` | CPI button (its default is `dpi`) |

## Limitations

- **Colors need this tool at plug-in.** According to SteelSeries and rivalcfg, the mouse stores CPI, polling rate, bindings, brightness and whether it starts `off` or in `rainbow`, but not colors. On another computer it shows only that startup state.
- **Keys are physical QWERTY positions.** On a Hungarian layout `z` and `y` are swapped, and some symbols differ.
- **One key per button.** Combinations such as Ctrl+C can't be bound.
- **`button7` to `button9` can't be used as actions**, because their ID in the device profile means "disabled". They can still be bound to something else.
- **Finding a pressed button depends on its binding.** The mouse reports what a button does, not which button it is. A `disabled` button sends nothing, which is the default for `button6` to `button8`, so bind one to something first to find it. If two buttons share an action, the first is selected. Unsaved bindings don't count until you save, because they aren't on the mouse yet.
- **Setting CPI selects the first preset.** The restore service never sends CPI, so this only happens when you change it.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

Tests need no mouse. To run the TUI against a simulated one, use `RIVALCFG_DRY=1 .venv/bin/rival5`.
