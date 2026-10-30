#!/usr/bin/env bash
# Install rival5 for this user, plus the udev rule (needs sudo) and restore service.
set -euo pipefail

cd "$(dirname "$0")"

python3 -m pip install --user .

sudo install -m 644 packaging/70-rival5.rules /etc/udev/rules.d/70-rival5.rules
sudo udevadm control --reload-rules

install -D -m 644 packaging/rival5-restore.service \
    "$HOME/.config/systemd/user/rival5-restore.service"
systemctl --user daemon-reload
systemctl --user enable rival5-restore.service

echo
echo "Done. Replug the mouse, then run: rival5"
