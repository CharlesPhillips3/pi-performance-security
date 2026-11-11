#!/bin/bash
# Remove the Security app and everything it changed
pkill -u "$USER" -x swayidle 2>/dev/null; pkill -u "$USER" -x xautolock 2>/dev/null
sed -i '/# >>> pi-security autolock >>>/,/# <<< pi-security autolock <<</d' ~/.config/labwc/autostart 2>/dev/null
sed -i '/^pi_security *=/d' ~/.config/wayfire.ini 2>/dev/null
rm -f ~/.config/autostart/security-idle.desktop ~/.local/bin/security-idle
command -v secret-tool >/dev/null && secret-tool clear service pi-security user "$USER"
sudo rm -f /etc/sudoers.d/60-pi-security /etc/polkit-1/rules.d/49-pi-security.rules \
  /usr/local/bin/pi-security /usr/local/bin/pi-sudo /usr/share/applications/pi-security.desktop \
  /usr/share/icons/hicolor/128x128/apps/pi-security.png
sudo rm -rf /opt/pi-security
rm -rf ~/.config/pi-security
echo "Security app removed. (RTC charging line in config.txt, if you added it, was left alone.)"
