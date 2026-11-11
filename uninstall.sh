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
sudo systemctl disable pi-security-power.service 2>/dev/null
sudo systemctl disable --now pi-powerlog.service 2>/dev/null
sudo /usr/local/sbin/pi-oc-tuner cancel 2>/dev/null
sudo systemctl disable pi-oc-tuner.service 2>/dev/null
sudo rm -f /etc/systemd/system/pi-oc-tuner.service /usr/local/sbin/pi-oc-tuner
sudo rm -f /etc/systemd/system/pi-powerlog.service /usr/local/sbin/pi-powerlog
sudo rm -rf /var/lib/pi-security
sudo rm -f /etc/systemd/system/fstrim.timer.d/pi-security.conf
sudo rm -f /etc/systemd/system/pi-security-power.service /usr/local/sbin/pi-security-power
sudo rm -rf /opt/pi-security /etc/pi-security
sudo systemctl daemon-reload
sudo systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null
rm -rf ~/.config/pi-security
echo "Pi-Performance / Security removed. (Sleep is re-enabled. CPU profile / Turbo Disk boot settings (config.txt, cmdline.txt), RTC charging, auto-login, SSH, VNC and firewall settings are left as they are.)"
