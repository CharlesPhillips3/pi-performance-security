# Pi-Performance / Security for Raspberry Pi 5

A small desktop app for Raspberry Pi OS (Bookworm / Trixie) with seven tabs:

| Power | Turbo Disk | Auto-Lock | Sleep |
|---|---|---|---|
| ![](screenshot-power.png) | ![](screenshot-disk.png) | ![](screenshot-autolock.png) | ![](screenshot-sleep.png) |

| Access | Login Once | Clock |
|---|---|---|
| ![](screenshot-access.png) | ![](screenshot-login.png) | ![](screenshot-clock.png) |

*(The Power screenshot shows example data.)*

## Power
- **Live readout**: CPU and GPU speed, governor, temperature, power draw in watts, and under-voltage / throttling warnings.
- **24-hour power graph** with average, min and peak watts, **kWh per day**, and estimated **cost per month and year** at your electric rate. The `pi-powerlog` service records the Pi 5's power chip once a minute, so the graph keeps filling while the app is closed. (It measures the Pi board and what it powers - a good estimate, not a wall-plug meter.)
- **CPU & graphics profiles**: **Save Energy** (`powersave`, graphics Eco 500 MHz), **Normal** (`ondemand`, stock), **Performance** (`performance`, CPU always at full speed).
- **CPU speed**: Stock 2.4 GHz, or OC 1-5 (2.6 / 2.7 / 2.8 / 2.9 / 3.0 GHz).
- **Graphics boost**: Eco 500 MHz, Stock 910 MHz, Boost 1 (1000), Boost 2 (1050), Boost 3 (1100).
- The governor changes instantly; the speeds go in a marked block in `config.txt` (backup saved) and need a reboot.
- **Overclock Finder**: finds the fastest CPU and graphics speeds **your** Pi runs safely, by itself:
  - Steps up one level per reboot and stress-tests each one: `stress-ng --verify` for the CPU (catches wrong answers, not just crashes) and `glmark2` for graphics.
  - A level passes only with no errors, no crash, no throttling, no under-voltage, and under 82 °C.
  - **Safe result = one step below the fastest that passed**, then CPU and graphics are checked together.
  - **Can't brick your setup**: each test speed is used for one boot only (Pi 5 *tryboot*) and the hardware watchdog restarts a frozen Pi back onto normal settings.
  - About 45-60 minutes and roughly 10 reboots. Keep a monitor plugged in for the graphics test. It can apply the safe result automatically, or you pick it from the dropdowns ("Safe (from Finder)").
  - Command line: `sudo pi-oc-tuner start | status | cancel`
- **Restart** and **Shut down** buttons.

## Turbo Disk
- Shows each NVMe drive, its model, and the PCIe link speed it's running at right now.
- **⚡ TURBO ON** puts the NVMe at full speed in one click:
  - **PCIe Gen 3** (about 2x faster than the default Gen 2)
  - **Keeps the drive awake**: no deep power-saving states, so no wake-up lag
  - **PCIe link power saving off** (ASPM)
  - **Bigger read-ahead** (2 MB) for fast big-file copies and backups
  - **Daily TRIM**
- **TRIM schedule**: Daily, Weekly (default) or Off, plus a **Run TRIM now** button.
- **Turbo OFF** puts everything back to stock. You can also set each option on its own.
- **Speed test**: reads 1 GB straight from the drive (read-only) and shows the MB/s.

## Auto-Lock
- Lock the screen after an idle time you set in **hours and minutes**, turn the monitor off a set time (hours + minutes) after it locks, and lock before the Pi sleeps.
- **Lock now** button (same as Ctrl+Alt+L).
- Wayland desktop (labwc / wayfire): uses `swayidle` + `swaylock` (+ `wlopm` for monitor off).
  X11 desktop: uses `light-locker` with the X screensaver timer.
- Starts at every login. Adds a marked block to `~/.config/labwc/autostart` (the rest of the file is left alone).

## Sleep
- **Sleep ENABLED / DISABLED** for the whole Pi (masks the systemd sleep targets). When it's disabled, nothing can put the Pi to sleep, which is the safe setting for an always-on Pi (servers, RAID, hotspot). The status line shows which sleep modes your Pi supports.
- **Put the Pi to sleep when idle** after a set time in hours + minutes (Wayland desktop; only while sleep is enabled).
- Raspberry Pi OS **screen blanking** on/off. Turn it off if you use the monitor-off timer on the Auto-Lock tab.

## Access
- **Desktop auto-login** on/off. With auto-login on, anyone who reboots the Pi gets in with no password, so the auto-lock doesn't protect you.
- **SSH** and **VNC** on/off, with live status.
- **Firewall (ufw)** on/off. "ON" keeps SSH (22) and VNC (5900) open so you can't lock yourself out, and blocks everything else coming in.
- **Login history**: failed and successful logins (SSH, sudo, desktop) from the last 7 days.
- **Updates**: check for and install system updates.

## Login Once
- **Save to keyring**: checks your password with sudo, then stores it **encrypted** in the login keyring (gnome-keyring). The keyring unlocks when you log in, so your password is entered once per login.
- **Skip the password prompt** for chosen admin commands (RAID/mdadm, smartctl, mounts, networking, systemctl, clock, Pi firmware/power, backups, or your own paths). Rules go in `/etc/sudoers.d/60-pi-security` and are checked with `visudo` before install, so a bad rule can't break sudo.
- Optional: all sudo commands without a password, and skip the graphical polkit prompt. Each of these has a warning.
- **`pi-sudo`**: use it in your own apps and scripts in place of `sudo`. It uses the saved password:
  ```bash
  pi-sudo mdadm --detail /dev/md0
  ```
  In Python:
  ```python
  pw = subprocess.run(["secret-tool","lookup","service","pi-security","user",getpass.getuser()],
                      capture_output=True, text=True).stdout
  ```

> Note: Raspberry Pi OS often gives the first user passwordless sudo already (`/etc/sudoers.d/010_pi-nopasswd`). The app shows "sudo never asks for a password" when that's the case.

## Clock
- Live clock with time zone, network-time sync status and RTC status.
- Set the **time zone**, turn **network time** (NTP) on/off, **Sync now**.
- Set the **date & time by hand** (turns NTP off first if needed).
- Pi 5 **RTC**: Read, Save system time to RTC, Load from RTC.
- **RTC battery charging** on/off (`dtparam=rtc_bbat_vchg=3000000` in config.txt). Only use this with a **rechargeable** ML-2020 cell, never a CR2032. Needs a reboot.
- **Taskbar clock**: 12-hour, 24-hour, or with seconds.

Every setting has an **i** button that explains what it does.

## Install
```bash
git clone https://github.com/CharlesPhillips3/pi-performance-security.git
cd pi-performance-security
bash install.sh
```
Open it from **Menu → Preferences → Pi-Performance / Security**, or run `pi-security`.
Log out and back in once after installing so the keyring unlocks at login.

## Update
Press **⟳ Update app** at the top right of the app. It downloads the newest version from GitHub, installs it, and offers to restart.
(From a terminal: `cd pi-performance-security && git pull && bash install.sh`)

## Uninstall
```bash
bash uninstall.sh
```
This removes the app, its autostart entry, the saved keyring password, and its sudoers/polkit rules, the power logger and its data, and re-enables sleep. Put Power on **Normal** and Turbo Disk **OFF** first if you want stock boot settings back. Auto-login, SSH, VNC, firewall and RTC settings stay as you left them.

## Files
| File | What it is |
|---|---|
| `security.py` | The app (Python 3 + Tkinter) |
| `pi-sudo` | Runs sudo with the password saved in the keyring |
| `pi-powerlog`, `pi-powerlog.service` | Background power-draw logger for the 24-hour graph |
| `pi-oc-tuner`, `pi-oc-tuner.service` | Overclock Finder (only active while tuning) |
| `install.sh` / `uninstall.sh` | Installer / remover |
| `security.desktop`, `security.png` | Menu entry and icon |

MIT License.
