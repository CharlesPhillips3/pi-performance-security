#!/bin/bash
# Install the Security app for the current user (Raspberry Pi OS Bookworm / Trixie)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Installing packages (needs sudo once)…"
sudo apt-get update
for p in python3-tk swayidle swaylock wlopm xautolock light-locker libsecret-tools gnome-keyring libpam-gnome-keyring; do
  sudo apt-get install -y "$p" || echo "  (skipped $p - not available on this OS)"
done
sudo install -Dm755 "$DIR/security.py" /opt/pi-security/security.py
sudo install -Dm755 "$DIR/pi-sudo" /usr/local/bin/pi-sudo
sudo install -Dm644 "$DIR/security.png" /usr/share/icons/hicolor/128x128/apps/pi-security.png 2>/dev/null || true
sudo install -Dm644 "$DIR/security.desktop" /usr/share/applications/pi-security.desktop
sudo ln -sf /opt/pi-security/security.py /usr/local/bin/pi-security
sudo gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true
echo
echo "Done. Open it from  Menu > Preferences > Security  (or run: pi-security)."
echo "Log out and back in once so the login keyring starts unlocking with your password."
