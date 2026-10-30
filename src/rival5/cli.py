"""The rival5 command. With no arguments it opens the TUI."""

import argparse
import sys

from . import config, device


def _parser():
    parser = argparse.ArgumentParser(
        prog="rival5", description="Configure a SteelSeries Rival 5."
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="try a change: don't touch the config or onboard memory",
    )
    commands = parser.add_subparsers(dest="command")

    command = commands.add_parser("color", help="set LED colors")
    command.add_argument("zone", help="all, left, right, logo, wheel or z0-z9")
    command.add_argument("color", help="#00aaff, 0af or a name like red")

    commands.add_parser("rainbow", help="rainbow effect")

    command = commands.add_parser("cpi", help="set CPI presets")
    command.add_argument("presets", nargs="+", type=int, metavar="CPI")

    command = commands.add_parser("poll", help="set polling rate")
    command.add_argument("rate", type=int)

    command = commands.add_parser("brightness", help="set LED brightness")
    command.add_argument("level", type=int)

    command = commands.add_parser("bind", help="bind buttons, keeping the others")
    command.add_argument("bindings", nargs="+", metavar="BUTTON=ACTION")
    command.add_argument("--force", action="store_true", help="allow no left click")

    command = commands.add_parser("unbind", help="return buttons to default")
    command.add_argument("buttons", nargs="*", metavar="BUTTON")
    command.add_argument("--all", action="store_true", help="all buttons")
    command.add_argument("--force", action="store_true", help="allow no left click")

    command = commands.add_parser("apply", help="send the whole config")
    command.add_argument("--force", action="store_true", help="allow no left click")

    commands.add_parser("restore", help="re-send lighting only (used by the service)")
    commands.add_parser("show", help="print the config")
    commands.add_parser("reset", help="factory defaults, clears the config")
    return parser


def _change(args, change, send, force=False):
    """Change the config, then send it. Only a success is written to disk."""
    cfg = config.load()
    change(cfg)
    config.validate(cfg, force=force)
    with device.open_mouse() as mouse:
        send(mouse, cfg)
        if send is not device.send_lighting and not args.no_save:
            mouse.save()
    if not args.no_save:
        config.save(cfg)


def _set_field(name, value):
    return lambda cfg: setattr(cfg, name, value)


def _bind_all(pairs):
    def change(cfg):
        for button, action in pairs:
            config.bind(cfg, button, action)

    return change


def _parse_binding(text):
    button, separator, action = text.partition("=")
    if not separator or not action:
        raise ValueError(f"Expected BUTTON=ACTION, got: {text}")
    return button, action


def _set_rainbow(cfg):
    cfg.rainbow = True


def _unbind(args):
    if args.all:
        return lambda cfg: cfg.buttons.clear()
    if not args.buttons:
        raise ValueError("Name a button, or use --all")
    return _bind_all([(button, "default") for button in args.buttons])


def _show():
    path = config.default_path()
    print(f"# {path} (the mouse can't be read back)\n")
    print(config.dumps(config.load()), end="")


def _restore():
    if not config.default_path().exists():
        return
    try:
        with device.open_mouse() as mouse:
            device.restore(mouse, config.load())
    except device.DeviceError as error:
        if str(error) != device.NOT_FOUND:
            raise


def _reset():
    with device.open_mouse() as mouse:
        device.reset(mouse)
    config.default_path().unlink(missing_ok=True)


def _apply(args):
    cfg = config.load()
    config.validate(cfg, force=args.force)
    with device.open_mouse() as mouse:
        device.apply(mouse, cfg, save=not args.no_save)


def run(args):
    match args.command:
        case "color":
            _change(
                args,
                lambda cfg: config.set_zone(cfg, args.zone, args.color),
                device.send_lighting,
            )
        case "rainbow":
            _change(args, _set_rainbow, device.send_lighting)
        case "cpi":
            _change(
                args,
                _set_field("sensitivity", args.presets),
                lambda mouse, cfg: mouse.set_sensitivity(cfg.sensitivity),
            )
        case "poll":
            _change(
                args,
                _set_field("polling", args.rate),
                lambda mouse, cfg: mouse.set_polling_rate(cfg.polling),
            )
        case "brightness":
            _change(
                args,
                _set_field("brightness", args.level),
                lambda mouse, cfg: mouse.set_led_brightness(cfg.brightness),
            )
        case "bind":
            pairs = [_parse_binding(text) for text in args.bindings]
            _change(args, _bind_all(pairs), device.send_buttons, args.force)
        case "unbind":
            _change(args, _unbind(args), device.send_buttons, args.force)
        case "apply":
            _apply(args)
        case "restore":
            _restore()
        case "show":
            _show()
        case "reset":
            _reset()


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command is None:
            from .tui import Rival5App

            Rival5App().run()
        else:
            run(args)
    except (ValueError, device.DeviceError, OSError) as error:
        print(f"rival5: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
