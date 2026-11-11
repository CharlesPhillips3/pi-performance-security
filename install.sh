#!/bin/bash
# Install Pi-Performance / Security for the current user (Raspberry Pi OS Bookworm / Trixie)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Installing packages (needs sudo once)…"
sudo apt-get update
for p in git python3-tk swayidle swaylock wlopm light-locker x11-xserver-utils libsecret-tools gnome-keyring libpam-gnome-keyring ufw; do
  sudo apt-get install -y "$p" || echo "  (skipped $p - not available on this OS)"
done
sudo install -Dm755 "$DIR/security.py" /opt/pi-security/security.py
echo "$DIR" | sudo tee /opt/pi-security/source-dir >/dev/null   # used by the app's Update button
sudo install -Dm755 "$DIR/pi-sudo" /usr/local/bin/pi-sudo
sudo install -Dm644 "$DIR/security.png" /usr/share/icons/hicolor/128x128/apps/pi-security.png 2>/dev/null || true
sudo install -Dm755 "$DIR/pi-powerlog" /usr/local/sbin/pi-powerlog
sudo install -Dm644 "$DIR/pi-powerlog.service" /etc/systemd/system/pi-powerlog.service
sudo systemctl daemon-reload
sudo systemctl enable --now pi-powerlog.service
sudo install -Dm644 "$DIR/security.desktop" /usr/share/applications/pi-security.desktop
sudo ln -sf /opt/pi-security/security.py /usr/local/bin/pi-security
sudo gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true
echo
echo "Done. Open it from  Menu > Preferences > Pi-Performance / Security  (or run: pi-security)."
echo "Log out and back in once so the login keyring starts unlocking with your password."
