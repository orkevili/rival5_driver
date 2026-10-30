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
| `+` `-` `a` `d` | On the CPI tab: step, add, remove |
| `s` | Save to the config and the mouse |
| `Ctrl+S` | Save, also from inside a text field |
| `q` | Quit |

Colors can be hex (`#00aaff`, `0af`), CSS names (`orange`, `hotpink`), `rgb(0,170,255)` or `hsl(200,100%,50%)`. LEDs don't match a screen exactly, so a color may look different on the mouse. `orange` and `pink` are adjusted for the LEDs; a hex value is always sent as written.

Colors change on the mouse as you pick them, as a preview. Everything else waits for `s`, and tabs with unsaved changes show `●`. If you quit and discard, the saved colors are put back.

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
- **Setting CPI selects the first preset.** The restore service never sends CPI, so this only happens when you change it.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

Tests need no mouse. To run the TUI against a simulated one, use `RIVALCFG_DRY=1 .venv/bin/rival5`.
