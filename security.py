#!/usr/bin/env python3
"""
Pi-Performance / Security - performance, power and security settings for Raspberry Pi 5.

Tabs:
  Auto-Lock  - lock the desktop after an idle time in hours + minutes (swayidle +
               swaylock on labwc/wayfire Wayland, light-locker on X11)
  Login Once - save your username/password in the login keyring (unlocked when
               you log in) and pick which admin commands skip the sudo prompt
  Clock      - timezone, network time, manual date/time, the Pi 5 RTC and
               its battery charger, taskbar clock format
"""

import datetime
import getpass
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import tkinter as tk
from tkinter import messagebox, ttk

APP_NAME = "Pi-Performance / Security"
REPO = "https://github.com/CharlesPhillips3/pi-performance-security"
SRC_FILE = "/opt/pi-security/source-dir"   # written by install.sh: where the git copy lives
VERSION = "1.5.0"
USER = getpass.getuser()
HOME = os.path.expanduser("~")
CONF_DIR = os.path.join(HOME, ".config", "pi-security")
CONF_FILE = os.path.join(CONF_DIR, "settings.json")
IDLE_SCRIPT = os.path.join(HOME, ".local", "bin", "security-idle")
LABWC_AUTOSTART = os.path.join(HOME, ".config", "labwc", "autostart")
WAYFIRE_INI = os.path.join(HOME, ".config", "wayfire.ini")
XDG_AUTOSTART = os.path.join(HOME, ".config", "autostart", "security-idle.desktop")
PANEL_INI = os.path.join(HOME, ".config", "wf-panel-pi.ini")
SUDOERS_FILE = "/etc/sudoers.d/60-pi-security"
POLKIT_FILE = "/etc/polkit-1/rules.d/49-pi-security.rules"
KEYRING_ATTRS = ["service", "pi-security", "user", USER]
MARK_BEGIN = "# >>> pi-security autolock >>>"
MARK_END = "# <<< pi-security autolock <<<"

# Admin commands the "Login Once" tab can let run without a sudo prompt.
SUDO_PRESETS = [
    ("RAID tools (mdadm)", ["/usr/sbin/mdadm"]),
    ("Disk health (smartctl)", ["/usr/sbin/smartctl"]),
    ("Disks & mounts (mount, umount, blkid, lsblk, fsck)",
     ["/usr/bin/mount", "/usr/bin/umount", "/usr/sbin/blkid", "/usr/bin/lsblk", "/usr/sbin/fsck"]),
    ("Networking (nmcli, ip, iptables)",
     ["/usr/bin/nmcli", "/usr/sbin/ip", "/usr/sbin/iptables", "/usr/sbin/nft"]),
    ("Services (systemctl)", ["/usr/bin/systemctl"]),
    ("Clock (timedatectl, hwclock, date)",
     ["/usr/bin/timedatectl", "/usr/sbin/hwclock", "/usr/bin/date"]),
    ("Pi firmware & power (rpi-eeprom-*, vcgencmd, reboot, shutdown)",
     ["/usr/bin/rpi-eeprom-update", "/usr/bin/rpi-eeprom-config", "/usr/bin/vcgencmd",
      "/usr/sbin/reboot", "/usr/sbin/shutdown"]),
    ("Backups (rsync, dd, tar)", ["/usr/bin/rsync", "/usr/bin/dd", "/usr/bin/tar"]),
]

INFO = {
    "autolock": "Locks the screen after you stop using the mouse and keyboard for "
                "the hours and minutes you choose. Unlock with your normal login password.",
    "screenoff": "Turns the monitor off a while after the lock kicks in, to save "
                 "power and screen life. Moving the mouse turns it back on.",
    "sleep": "Also locks the screen right before the Pi suspends, so nobody "
             "wakes it up to an open desktop.",
    "keyring": "Your password is saved encrypted in the login keyring "
               "(gnome-keyring). It unlocks automatically when you log in to the "
               "desktop, so your own apps can read it with:\n\n"
               "  secret-tool lookup service pi-security user " + USER + "\n\n"
               "It is never written to a plain text file.",
    "sudo": "Ticked commands are added to " + SUDOERS_FILE + " so `sudo <command>` "
            "runs without asking for your password. The file is checked with "
            "visudo before it is installed, so it cannot break sudo.",
    "fullsudo": "Lets EVERY sudo command run without a password. Convenient, "
                "but anyone at your unlocked desktop then has full control of the Pi. "
                "Keep auto-lock on if you use this.",
    "polkit": "Skips the graphical 'Authentication required' pop-up (pkexec / "
              "polkit) for your user. Same trade-off as full sudo.",
    "sysleep": "Turns system sleep (suspend) on or off for the whole Pi by masking "
               "the systemd sleep targets. When it's off, nothing - not the menu, "
               "not an app, not the idle timer - can put the Pi to sleep. "
               "Note: the Pi 5 has only limited suspend support, so 'off' is the "
               "safe setting for an always-on Pi (servers, RAID, hotspot).",
    "idlesleep": "Puts the Pi to sleep after this much idle time. Works on the "
                 "default Wayland desktop. Only runs while system sleep is enabled.",
    "blank": "Raspberry Pi OS's own screen blanking (Raspberry Pi Configuration > "
             "Display). Turn it OFF if you use the monitor-off timer on the "
             "Auto-Lock tab, so the two don't fight. Needs a reboot or re-login.",
    "power": "Restart or shut down the Pi. You'll be asked to confirm first.",
    "autologin": "With auto-login ON the Pi goes straight to the desktop at boot, "
                 "with no password. That means anyone who reboots it gets in, "
                 "and the auto-lock doesn't help. Turn it OFF so a password is "
                 "needed after every boot.",
    "ssh": "SSH lets you log in to the Pi remotely from a terminal. Turn it off "
           "if you never use it - fewer open doors.",
    "vnc": "VNC (wayvnc / RealVNC) lets you see and control the desktop "
           "remotely. Turn it off if you don't use remote desktop.",
    "ufw": "A firewall (ufw) blocks incoming connections you didn't ask for. "
           "'Firewall ON' keeps SSH (22) and VNC (5900) open so you can't lock "
           "yourself out, and blocks everything else coming in.",
    "fails": "Shows failed and successful logins (SSH, sudo, desktop) from the "
             "last 7 days, so you can spot someone trying to get in.",
    "updates": "Checks for and installs software updates (apt full-upgrade). "
               "Keeping the Pi updated is the best single security step.",
    "powergraph": "Power draw of the Pi 5 board, measured by its own power chip once a minute "
                  "by the pi-powerlog service (it keeps logging while this app is closed). "
                  "It counts the Pi itself - the CPU, memory, USB and NVMe rails it powers - so it's a "
                  "good estimate, but not the same as a wall-plug meter (it leaves out power supply losses "
                  "and anything with its own power). kWh/day = average watts x 24 / 1000.",
    "overclock": "Adds arm_freq=2800 (CPU 2.4 to 2.8 GHz) and gpu_freq=1000 to config.txt. "
                 "Needs a fan / active cooler and the official 27 W power supply. If the "
                 "Pi won't boot, hold SHIFT at boot or remove those lines from config.txt "
                 "on another computer. A backup is saved as config.txt.bak-security.",
    "throttle": "If the Pi gets too hot (about 80-85 C) or the power supply is too weak, "
                "the firmware slows it down. 'Under-voltage' means use a better supply.",
    "gen3": "The Pi 5's PCIe slot runs at Gen 2 (about 450 MB/s) by default. Gen 3 roughly "
            "doubles NVMe speed (about 800-900 MB/s). It isn't officially certified, "
            "but works with most NVMe HATs and drives. Needs a reboot. If the drive "
            "acts up, turn it back off.",
    "apst": "NVMe drives drop into deep power-saving states when idle, which adds "
            "lag when they wake up. This keeps the drive fully awake "
            "(nvme_core.default_ps_max_latency_us=0 in cmdline.txt). Needs a reboot.",
    "aspm": "PCIe link power saving (ASPM). Turning it off keeps the PCIe link at full "
            "power - smoother speed, a little more power use. Needs a reboot.",
    "readahead": "How much the kernel reads ahead on big sequential reads. "
                 "Bigger = faster large file copies and backups. Changes right away "
                 "and is kept after a reboot.",
    "trim": "Weekly TRIM tells the SSD which blocks are free, keeping it fast "
            "over time (systemd fstrim.timer).",
    "speedtest": "Reads 1 GB straight from the drive (read-only - it doesn't change "
                 "anything) to measure its real speed.",
    "ntp": "Network time keeps the clock correct automatically from the internet "
           "(systemd-timesyncd). Turn it off only if you want to set the time by hand.",
    "rtc": "The Pi 5 has a built-in real-time clock. With a battery on the J5 'BAT' "
           "connector it keeps time while unplugged. 'Save to RTC' copies the "
           "system time into it.",
    "charge": "Only for a RECHARGEABLE lithium-manganese cell (e.g. the official "
              "ML-2020 battery). Never enable with a normal CR2032 coin cell. "
              "Adds dtparam=rtc_bbat_vchg=3000000 to config.txt; needs a reboot.",
    "panel": "Sets how the clock looks on the taskbar (strftime format, e.g. "
             "%I:%M %p for 1:15 PM, %H:%M for 13:15).",
}


# --------------------------------------------------------------------------- helpers
def run(cmd, inp=None, timeout=20):
    """Run a command, return (returncode, stdout+stderr)."""
    try:
        p = subprocess.run(cmd, input=inp, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not installed"
    except subprocess.TimeoutExpired:
        return 124, f"{cmd[0]}: timed out"


def have(prog):
    return shutil.which(prog) is not None


def load_settings():
    d = {"autolock": False, "lock_min": 5, "screenoff": True, "off_min": 2,
         "lock_sleep": True, "idle_sleep": False, "sleep_min": 60, "presets": [], "custom": "", "fullsudo": False,
         "polkit": False}
    try:
        with open(CONF_FILE) as f:
            d.update(json.load(f))
    except Exception:
        pass
    return d


def save_settings(d):
    os.makedirs(CONF_DIR, exist_ok=True)
    with open(CONF_FILE, "w") as f:
        json.dump(d, f, indent=2)


def keyring_get():
    if not have("secret-tool"):
        return None
    rc, out = run(["secret-tool", "lookup", *KEYRING_ATTRS])
    return out if rc == 0 and out else None


BOOT = "/boot/firmware" if os.path.isdir("/boot/firmware") else "/boot"
CONFIG_TXT = os.path.join(BOOT, "config.txt")
CMDLINE_TXT = os.path.join(BOOT, "cmdline.txt")
POWER_HELPER = "/usr/local/sbin/pi-security-power"
POWER_UNIT = "/etc/systemd/system/pi-security-power.service"
POWER_STATE = "/etc/pi-security"
POWER_LOG = "/var/lib/pi-security/power.csv"


def pmic_watts():
    """Pi 5 board power from the PMIC: sum of volts x amps over every rail (None if unavailable)."""
    out = vc("pmic_read_adc")
    amps, volts = {}, {}
    for name, kind, val in re.findall(r"(\S+)_(A|V)\s+\w+\(\d+\)=([\d.]+)", out):
        (amps if kind == "A" else volts)[name] = float(val)
    return sum(a * volts[n] for n, a in amps.items() if n in volts) if amps else None


def power_history(hours=24):
    cut = time.time() - hours * 3600
    pts = []
    try:
        with open(POWER_LOG) as f:
            for line in f:
                t, _, w = line.strip().partition(",")
                if t.isdigit() and int(t) >= cut:
                    try:
                        pts.append((int(t), float(w)))
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass
    return pts

# CPU/GPU profiles. governor = live (no reboot); config = lines put in config.txt (reboot)
PROFILES = {
    "save": {"name": "Save Energy", "governor": "powersave",
             "config": ["# Save Energy: CPU held at its lowest speed, GPU slowed down",
                        "gpu_freq=500"],
             "desc": "Lowest CPU speed and a slower GPU. Runs cooler and quieter and "
                     "uses the least power - fine for servers, RAID, hotspot and "
                     "background jobs."},
    "normal": {"name": "Normal", "governor": "ondemand", "config": [],
               "desc": "Raspberry Pi OS default. The CPU speeds up when there's work "
                       "and slows down when idle. Stock GPU speed."},
    "perf": {"name": "Performance", "governor": "performance",
             "config": ["# Performance: CPU always at full speed"],
             "desc": "CPU stays at full speed all the time - snappier desktop, faster "
                     "builds, but more heat and power. Tick 'Overclock' for even more."},
}
INFO["profile"] = ("\n\n".join(f"{p['name']}: {p['desc']}" for p in PROFILES.values())
                   + "\n\nThe CPU part changes right away and is kept after a reboot. "
                     "The GPU part goes in config.txt and needs a reboot.")
OVERCLOCK = ["# Overclock (needs good cooling and the 27 W power supply)",
             "arm_freq=2800", "gpu_freq=1000"]


def read_sys(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return default


def vc(*args):
    rc, out = run(["vcgencmd", *args])
    return out if rc == 0 else ""


def nvme_devices():
    """[(name, pci_dir)] for each NVMe drive."""
    out = []
    base = "/sys/class/nvme"
    for n in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        dev = os.path.realpath(os.path.join(base, n, "device"))
        out.append((n, dev))
    return out


SLEEP_TARGETS = ["sleep.target", "suspend.target", "hibernate.target", "hybrid-sleep.target"]


def sleep_allowed():
    """False if the Security app (or anyone) masked the systemd sleep targets."""
    rc, out = run(["systemctl", "is-enabled", "suspend.target"])
    return "masked" not in out


def sleep_supported():
    try:
        st = open("/sys/power/state").read().split()
    except Exception:
        st = []
    return st


def raspi(*args):
    """raspi-config non-interactive helper (needs root)."""
    return ["raspi-config", "nonint", *args]


def session_type():
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return "wayland"
    return "x11"


class Root:
    """Runs commands as root: sudo -n first, then the keyring password, then asks."""

    def __init__(self, app):
        self.app = app
        self.cached = None

    def _password(self):
        if self.cached:
            return self.cached
        pw = keyring_get()
        if pw and self._check(pw):
            self.cached = pw
            return pw
        pw = self.app.ask_password()
        if pw and self._check(pw):
            self.cached = pw
            return pw
        if pw:
            messagebox.showerror(APP_NAME, "That password was not accepted by sudo.")
        return None

    @staticmethod
    def _check(pw):
        rc, _ = run(["sudo", "-S", "-k", "-p", "", "-v"], inp=pw + "\n")
        return rc == 0

    def ensure(self):
        """Make sure root commands will work (asks for the password now if needed).
        Call this on the main thread before starting a background job."""
        if run(["sudo", "-n", "true"])[0] == 0:
            return True
        return self._password() is not None

    def run(self, cmd, inp=None, timeout=60):
        rc, out = run(["sudo", "-n", *cmd], inp=inp, timeout=timeout)
        if rc == 0 or "password" not in out.lower():
            return rc, out
        pw = self._password()
        if not pw:
            return 1, "Cancelled - administrator password needed."
        data = pw + "\n" + (inp or "")
        return run(["sudo", "-S", "-p", "", *cmd], inp=data, timeout=timeout)

    def write_file(self, path, text, mode="0440"):
        with tempfile.NamedTemporaryFile("w", delete=False) as t:
            t.write(text)
            tmp = t.name
        try:
            return self.run(["install", "-m", mode, "-o", "root", "-g", "root", tmp, path])
        finally:
            os.unlink(tmp)


# --------------------------------------------------------------------------- app
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}")
        self.geometry("800x820")
        self.minsize(560, 420)
        self.s = load_settings()
        self.root_cmd = Root(self)
        self._style()

        head = ttk.Frame(self, padding=(16, 12, 16, 4))
        head.pack(fill="x")
        ttk.Label(head, text="\U0001F512  Pi-Performance / Security", style="H1.TLabel").pack(side="left")
        ttk.Button(head, text="⟳ Update app", command=self.update_app).pack(side="right", padx=(8, 0))
        ttk.Label(head, text=f"v{VERSION} · {USER} · {session_type()}",
                  style="Dim.TLabel").pack(side="right")

        self.nb = nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(4, 0))
        pages = []
        for name in (" Auto-Lock ", " Sleep ", " Power ", " Turbo Disk ", " Access ", " Login Once ", " Clock "):
            outer, inner = self._scroller(nb)
            nb.add(outer, text=name)
            pages.append(inner)
        (self.tab_lock, self.tab_sleep, self.tab_power, self.tab_disk,
         self.tab_access, self.tab_login, self.tab_clock) = pages

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status, style="Status.TLabel",
                  anchor="w", padding=(14, 6)).pack(fill="x", side="bottom")

        self.build_lock()
        self.build_sleep()
        self.build_power()
        self.build_disk()
        self.build_access()
        self.build_login()
        self.build_clock()
        self.tick()
        if os.environ.get("PI_SECURITY_TAB", "").isdigit():  # open on a given tab (0-2)
            nb.select(int(os.environ["PI_SECURITY_TAB"]))

    def _scroller(self, parent):
        """A tab page that scrolls if the screen is small (e.g. the 7" touch display)."""
        outer = ttk.Frame(parent)
        cv = tk.Canvas(outer, highlightthickness=0, bg="#f6f7f9")
        sb = ttk.Scrollbar(outer, orient="vertical", command=cv.yview)
        inner = ttk.Frame(cv, padding=14)
        win = cv.create_window(0, 0, window=inner, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)

        def fit(_=None):
            cv.configure(scrollregion=cv.bbox("all"))
            cv.itemconfigure(win, width=cv.winfo_width())
            if inner.winfo_reqheight() > cv.winfo_height():
                sb.pack(side="right", fill="y")
            else:
                sb.pack_forget()
        inner.bind("<Configure>", fit)
        cv.bind("<Configure>", fit)
        for seq, d in (("<Button-4>", -1), ("<Button-5>", 1)):
            outer.bind_all(seq, lambda e, d=d: cv.yview_scroll(d, "units")
                           if str(e.widget).startswith(str(outer)) else None)
        return outer, inner

    # ---- look
    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        bg, fg, acc = "#f6f7f9", "#1d2430", "#c51a4a"  # raspberry accent
        self.configure(bg=bg)
        st.configure(".", background=bg, foreground=fg, font=("DejaVu Sans", 10))
        st.configure("TNotebook", background=bg, borderwidth=0)
        st.configure("TNotebook.Tab", padding=(10, 6))
        st.map("TNotebook.Tab", background=[("selected", "#ffffff")])
        st.configure("TFrame", background=bg)
        st.configure("Card.TLabelframe", background=bg, padding=8)
        st.configure("Card.TLabelframe.Label", font=("DejaVu Sans", 10, "bold"), foreground=fg)
        st.configure("H1.TLabel", font=("DejaVu Sans", 15, "bold"))
        st.configure("Dim.TLabel", foreground="#6b7280")
        st.configure("Big.TLabel", font=("DejaVu Sans Mono", 22, "bold"))
        st.configure("Status.TLabel", background="#e8ebf0", foreground="#374151")
        st.configure("Ok.TLabel", foreground="#15803d", font=("DejaVu Sans", 10, "bold"))
        st.configure("Bad.TLabel", foreground="#b91c1c", font=("DejaVu Sans", 10, "bold"))
        st.configure("Accent.TButton", background=acc, foreground="white", padding=(12, 5))
        st.map("Accent.TButton", background=[("active", "#a3153c")])
        st.configure("Info.TButton", padding=(2, 0), width=2)

    def update_app(self):
        """Pull the newest version from GitHub and re-run the installer."""
        src = read_sys(SRC_FILE)
        if not src or not os.path.isdir(os.path.join(src, ".git")):
            src = os.path.join(HOME, "pi-performance-security")
        if not have("git"):
            messagebox.showerror(APP_NAME, "git is not installed (sudo apt install git).")
            return
        if not messagebox.askyesno(APP_NAME, f"Download the newest version from GitHub and install it?\n\n{REPO}"):
            return
        if not self.root_cmd.ensure():
            return

        def job():
            if os.path.isdir(os.path.join(src, ".git")):
                run(["git", "-C", src, "remote", "set-url", "origin", REPO + ".git"])
                rc, out = run(["git", "-C", src, "pull", "--ff-only"], timeout=180)
                if rc != 0:  # local edits or odd state: take GitHub's copy
                    run(["git", "-C", src, "fetch", "origin"], timeout=180)
                    rc, out = run(["git", "-C", src, "reset", "--hard", "origin/main"], timeout=60)
            else:
                rc, out = run(["git", "clone", REPO + ".git", src], timeout=300)
            if rc != 0:
                return rc, out
            rc, out2 = self.root_cmd.run(["bash", os.path.join(src, "install.sh")], timeout=1800)
            new = re.search(r'^VERSION = "([^"]+)"', read_sys(os.path.join(src, "security.py")), re.M)
            self._new_ver = new.group(1) if new else "?"
            return rc, out + "\n" + out2

        def done():
            v = getattr(self, "_new_ver", None)
            if v and v != VERSION:
                if messagebox.askyesno(APP_NAME, f"Updated v{VERSION} → v{v}.\nRestart the app now?"):
                    os.execv("/usr/local/bin/pi-security", ["pi-security"])
            elif v:
                messagebox.showinfo(APP_NAME, f"You already have the newest version (v{v}).")
        self.bg(job, "Update finished.", "Updating from GitHub… (this can take a few minutes)", after=done)

    def info_btn(self, parent, key):
        return ttk.Button(parent, text="i", style="Info.TButton",
                          command=lambda: messagebox.showinfo(APP_NAME, INFO[key]))

    def say(self, msg):
        self.status.set(msg)
        self.update_idletasks()

    def ask_password(self):
        dlg = tk.Toplevel(self)
        dlg.title("Administrator password")
        dlg.transient(self)
        dlg.grab_set()
        ttk.Label(dlg, text=f"Password for {USER}:", padding=(14, 12, 14, 4)).pack(anchor="w")
        v = tk.StringVar()
        e = ttk.Entry(dlg, textvariable=v, show="•", width=32)
        e.pack(padx=14)
        e.focus_set()
        res = {"pw": None}

        def ok(*_):
            res["pw"] = v.get()
            dlg.destroy()

        bar = ttk.Frame(dlg, padding=12)
        bar.pack(fill="x")
        ttk.Button(bar, text="Cancel", command=dlg.destroy).pack(side="right")
        ttk.Button(bar, text="OK", style="Accent.TButton", command=ok).pack(side="right", padx=6)
        e.bind("<Return>", ok)
        self.wait_window(dlg)
        return res["pw"]

    # ================================================================ AUTO-LOCK
    def build_lock(self):
        t = self.tab_lock
        box = ttk.Labelframe(t, text="Lock the screen automatically", style="Card.TLabelframe")
        box.pack(fill="x")

        self.v_auto = tk.BooleanVar(value=self.s["autolock"])
        lm, om = int(self.s["lock_min"]), int(self.s["off_min"])
        self.v_lhr = tk.IntVar(value=lm // 60)
        self.v_lmin = tk.IntVar(value=lm % 60)
        self.v_off = tk.BooleanVar(value=self.s["screenoff"])
        self.v_ohr = tk.IntVar(value=om // 60)
        self.v_omin = tk.IntVar(value=om % 60)
        self.v_sleep = tk.BooleanVar(value=self.s["lock_sleep"])

        r = ttk.Frame(box); r.pack(fill="x", pady=3)
        ttk.Checkbutton(r, text="Lock the screen when idle", variable=self.v_auto).pack(side="left")
        self.info_btn(r, "autolock").pack(side="right")
        self._hm_row(box, "Idle time:", self.v_lhr, self.v_lmin, 24)

        r = ttk.Frame(box); r.pack(fill="x", pady=3)
        ttk.Checkbutton(r, text="Turn the monitor off after locking", variable=self.v_off).pack(side="left")
        self.info_btn(r, "screenoff").pack(side="right")
        self._hm_row(box, "Wait:", self.v_ohr, self.v_omin, 24)

        r = ttk.Frame(box); r.pack(fill="x", pady=3)
        ttk.Checkbutton(r, text="Lock before the Pi goes to sleep", variable=self.v_sleep).pack(side="left")
        self.info_btn(r, "sleep").pack(side="right")

        bar = ttk.Frame(t); bar.pack(fill="x", pady=12)
        ttk.Button(bar, text="Apply", style="Accent.TButton", command=self.apply_lock).pack(side="left")
        ttk.Button(bar, text="Lock now", command=self.lock_now).pack(side="left", padx=8)
        ttk.Button(bar, text="Install lock tools", command=self.install_tools).pack(side="right")

        st = ttk.Labelframe(t, text="Status", style="Card.TLabelframe")
        st.pack(fill="x")
        self.lock_status = ttk.Label(st, text="")
        self.lock_status.pack(anchor="w")
        self.refresh_lock_status()

    @staticmethod
    def _hm_row(parent, label, v_h, v_m, max_h):
        r = ttk.Frame(parent); r.pack(fill="x", pady=(0, 6), padx=(24, 0))
        ttk.Label(r, text=label, width=10).pack(side="left")
        ttk.Spinbox(r, from_=0, to=max_h, width=4, textvariable=v_h).pack(side="left")
        ttk.Label(r, text="hours").pack(side="left", padx=(4, 12))
        ttk.Spinbox(r, from_=0, to=59, width=4, textvariable=v_m).pack(side="left")
        ttk.Label(r, text="minutes").pack(side="left", padx=4)

    def _total_min(self, v_h, v_m):
        """Hours + minutes from the boxes, as whole minutes (at least 1)."""
        return max(1, int(v_h.get()) * 60 + int(v_m.get()))

    @staticmethod
    def _fmt(mins):
        h, m = divmod(mins, 60)
        return " ".join(x for x in (f"{h} h" if h else "", f"{m} min" if m else "") if x)

    def refresh_lock_status(self):
        if session_type() == "wayland":
            need = ["swayidle", "swaylock"]
        else:
            need = ["light-locker", "xset"]
        missing = [p for p in need if not have(p)]
        running = run(["pgrep", "-u", USER, "-x", need[0]])[0] == 0
        lines = [f"Desktop session: {session_type()}  (uses {need[0]} + {need[1]})"]
        lines.append("Missing tools: " + ", ".join(missing) if missing else "Lock tools: installed")
        lines.append(f"Idle watcher: {'running' if running else 'not running'}")
        self.lock_status.config(text="\n".join(lines))

    def install_tools(self):
        pk = ["swayidle", "swaylock", "wlopm", "light-locker", "x11-xserver-utils",
              "libsecret-tools", "gnome-keyring", "libpam-gnome-keyring"]
        if not messagebox.askyesno(APP_NAME, "Install:\n  " + " ".join(pk) + "\n\nwith apt?"):
            return
        self.say("Installing… this can take a minute.")
        self.root_cmd.run(["apt-get", "update"])
        # install one at a time so a package missing on this OS release doesn't block the rest
        bad = [p for p in pk if self.root_cmd.run(["apt-get", "install", "-y", p])[0] != 0]
        self.say("Installed." if not bad else "Installed, except: " + ", ".join(bad))
        self.refresh_lock_status()

    def write_idle_script(self):
        """One idle watcher for auto-lock, monitor-off and sleep-after-idle."""
        c = self.s
        lock = c["autolock"]
        lock_s = int(c["lock_min"]) * 60
        off_s = lock_s + int(c["off_min"]) * 60
        sleep_on = c["idle_sleep"] and sleep_allowed()
        sleep_s = int(c["sleep_min"]) * 60
        way = []
        if lock:
            way.append(f"timeout {lock_s} 'swaylock -f -c 1d2430'")
            if c["screenoff"]:
                way.append(f"timeout {off_s} 'wlopm --off \\*' resume 'wlopm --on \\*'")
        if sleep_on:
            way.append(f"timeout {sleep_s} 'systemctl suspend'")
        if lock and c["lock_sleep"]:
            way.append("before-sleep 'swaylock -f -c 1d2430'")
        way_cmd = "exec swayidle -w " + " ".join(way) + " >/dev/null 2>&1" if way else "exit 0"
        if lock:
            dpms = (f"xset +dpms dpms {off_s} {off_s} {off_s}" if c["screenoff"] else "xset -dpms")
            susp = "--lock-on-suspend" if c["lock_sleep"] else "--no-lock-on-suspend"
            x_cmd = (f"xset s {lock_s} 0\n  {dpms}\n"
                     f"  exec light-locker --lock-after-screensaver=0 {susp} >/dev/null 2>&1")
        else:
            x_cmd = "xset s off\n  exit 0"
        sh = f"""#!/bin/sh
# Generated by the Security app - re-written every time you press Apply.
pkill -u "$USER" -x swayidle 2>/dev/null
pkill -u "$USER" -x xautolock 2>/dev/null
pkill -u "$USER" -x light-locker 2>/dev/null
[ -f "$HOME/.config/pi-security/disabled" ] && exit 0
if [ -n "$WAYLAND_DISPLAY" ]; then
  {way_cmd}
else
  # X screensaver timer drives light-locker (works for any number of hours)
  {x_cmd}
fi
"""
        os.makedirs(os.path.dirname(IDLE_SCRIPT), exist_ok=True)
        with open(IDLE_SCRIPT, "w") as f:
            f.write(sh)
        os.chmod(IDLE_SCRIPT, 0o755)

    def restart_idle(self):
        """Rewrite the idle watcher and (re)start it, or stop it if nothing needs it."""
        flag = os.path.join(CONF_DIR, "disabled")
        os.makedirs(CONF_DIR, exist_ok=True)
        self.write_idle_script()
        needed = self.s["autolock"] or (self.s["idle_sleep"] and sleep_allowed())
        if needed:
            if os.path.exists(flag):
                os.remove(flag)
            self.hook_autostart(True)
            subprocess.Popen([IDLE_SCRIPT], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            open(flag, "w").close()
            self.hook_autostart(False)
            for p in ("swayidle", "xautolock", "light-locker"):
                run(["pkill", "-u", USER, "-x", p])
            if session_type() == "x11":
                run(["xset", "s", "off"])
        self.after(800, self.refresh_lock_status)
        return needed

    @staticmethod
    def _strip_block(text):
        return re.sub(re.escape(MARK_BEGIN) + r".*?" + re.escape(MARK_END) + r"\n?",
                      "", text, flags=re.S)

    def hook_autostart(self, enable):
        # labwc (Raspberry Pi OS default since late 2024)
        try:
            txt = open(LABWC_AUTOSTART).read()
        except FileNotFoundError:
            txt = ""
        txt = self._strip_block(txt)
        if enable:
            if txt and not txt.endswith("\n"):
                txt += "\n"
            txt += f"{MARK_BEGIN}\n{IDLE_SCRIPT} &\n{MARK_END}\n"
        os.makedirs(os.path.dirname(LABWC_AUTOSTART), exist_ok=True)
        with open(LABWC_AUTOSTART, "w") as f:
            f.write(txt)
        # wayfire (older Bookworm) - only touch it if the file exists
        if os.path.exists(WAYFIRE_INI):
            w = open(WAYFIRE_INI).read()
            w = re.sub(r"^pi_security\s*=.*\n?", "", w, flags=re.M)
            if enable:
                if "[autostart]" in w:
                    w = w.replace("[autostart]", f"[autostart]\npi_security = {IDLE_SCRIPT}", 1)
                else:
                    w += f"\n[autostart]\npi_security = {IDLE_SCRIPT}\n"
            open(WAYFIRE_INI, "w").write(w)
        # X11 sessions use XDG autostart
        if enable and session_type() == "x11":
            os.makedirs(os.path.dirname(XDG_AUTOSTART), exist_ok=True)
            with open(XDG_AUTOSTART, "w") as f:
                f.write(f"[Desktop Entry]\nType=Application\nName=Security idle lock\n"
                        f"Exec={IDLE_SCRIPT}\nOnlyShowIn=LXDE-pi-x;LXDE;\n")
        elif not enable and os.path.exists(XDG_AUTOSTART):
            os.remove(XDG_AUTOSTART)

    def apply_lock(self):
        try:
            self.s.update(autolock=self.v_auto.get(),
                          lock_min=self._total_min(self.v_lhr, self.v_lmin),
                          screenoff=self.v_off.get(),
                          off_min=self._total_min(self.v_ohr, self.v_omin),
                          lock_sleep=self.v_sleep.get())
        except (tk.TclError, ValueError):
            messagebox.showerror(APP_NAME, "Hours and minutes must be whole numbers.")
            return
        save_settings(self.s)
        self.restart_idle()
        if self.s["autolock"]:
            self.say(f"Auto-lock on: locks after {self._fmt(self.s['lock_min'])} idle. Starts at every login.")
        else:
            self.say("Auto-lock off.")

    def lock_now(self):
        if session_type() == "wayland" and have("swaylock"):
            subprocess.Popen(["swaylock", "-f", "-c", "1d2430"], start_new_session=True)
        elif have("light-locker-command"):
            subprocess.Popen(["light-locker-command", "-l"])
        elif have("loginctl"):
            run(["loginctl", "lock-session"])
        else:
            messagebox.showwarning(APP_NAME, "No lock tool found. Press 'Install lock tools'.")

    # ================================================================ SLEEP & POWER
    def build_sleep(self):
        t = self.tab_sleep
        box = ttk.Labelframe(t, text="System sleep", style="Card.TLabelframe")
        box.pack(fill="x")
        r = ttk.Frame(box); r.pack(fill="x")
        ttk.Button(r, text="Sleep ENABLED", command=lambda: self.set_sleep(True)).pack(side="left")
        ttk.Button(r, text="Sleep DISABLED", command=lambda: self.set_sleep(False)).pack(side="left", padx=6)
        self.info_btn(r, "sysleep").pack(side="right")
        self.sleep_status = ttk.Label(box, text="")
        self.sleep_status.pack(anchor="w", pady=(6, 0))

        r = ttk.Frame(box); r.pack(fill="x", pady=(10, 2))
        self.v_isleep = tk.BooleanVar(value=self.s["idle_sleep"])
        ttk.Checkbutton(r, text="Put the Pi to sleep when idle", variable=self.v_isleep).pack(side="left")
        self.info_btn(r, "idlesleep").pack(side="right")
        sm = int(self.s["sleep_min"])
        self.v_shr = tk.IntVar(value=sm // 60)
        self.v_smin = tk.IntVar(value=sm % 60)
        self._hm_row(box, "Idle time:", self.v_shr, self.v_smin, 24)
        ttk.Button(box, text="Apply", style="Accent.TButton", command=self.apply_idle_sleep).pack(anchor="w")

        bl = ttk.Labelframe(t, text="Screen blanking (Raspberry Pi OS setting)", style="Card.TLabelframe")
        bl.pack(fill="x", pady=(10, 0))
        r = ttk.Frame(bl); r.pack(fill="x")
        ttk.Button(r, text="Blanking ON", command=lambda: self.raspi_toggle("do_blanking", True, "Screen blanking")).pack(side="left")
        ttk.Button(r, text="Blanking OFF", command=lambda: self.raspi_toggle("do_blanking", False, "Screen blanking")).pack(side="left", padx=6)
        self.info_btn(r, "blank").pack(side="right")

        self.refresh_power()

    def refresh_power(self):
        allowed = sleep_allowed()
        states = sleep_supported()
        sup = ("sleep modes on this Pi: " + ", ".join(states)) if states else "this Pi reports no sleep modes"
        self.sleep_status.config(
            text=f"{'Sleep is ENABLED' if allowed else 'Sleep is DISABLED'}   ·   {sup}",
            style="TLabel" if allowed else "Ok.TLabel")

    def set_sleep(self, on):
        verb = "unmask" if on else "mask"
        rc, out = self.root_cmd.run(["systemctl", verb, *SLEEP_TARGETS])
        self._done(rc, out, "System sleep enabled." if on else "System sleep disabled - nothing can put the Pi to sleep.")
        self.restart_idle()
        self.refresh_power()

    def apply_idle_sleep(self):
        try:
            self.s.update(idle_sleep=self.v_isleep.get(),
                          sleep_min=self._total_min(self.v_shr, self.v_smin))
        except (tk.TclError, ValueError):
            messagebox.showerror(APP_NAME, "Hours and minutes must be whole numbers.")
            return
        save_settings(self.s)
        if self.s["idle_sleep"] and not sleep_allowed():
            messagebox.showwarning(APP_NAME, "System sleep is disabled, so this won't do anything "
                                             "until you press 'Sleep ENABLED'.")
        self.restart_idle()
        self.say(f"Sleep when idle: {'on, after ' + self._fmt(self.s['sleep_min']) if self.s['idle_sleep'] else 'off'}.")

    def raspi_toggle(self, fn, on, name):
        if not have("raspi-config"):
            messagebox.showerror(APP_NAME, "raspi-config not found (it comes with Raspberry Pi OS).")
            return
        # raspi-config: 0 = enable, 1 = disable
        rc, out = self.root_cmd.run(raspi(fn, "0" if on else "1"))
        self._done(rc, out, f"{name} {'on' if on else 'off'}.")
        if hasattr(self, "access_rows"):
            self.after(500, self.refresh_access)

    def power(self, what):
        word = "restart" if what == "reboot" else "shut down"
        if messagebox.askyesno(APP_NAME, f"{word.capitalize()} the Pi now?\nSave your work first."):
            rc, out = self.root_cmd.run(["systemctl", what])
            if rc != 0:
                messagebox.showerror(APP_NAME, out)

    # ================================================================ POWER (CPU / GPU)
    def build_power(self):
        t = self.tab_power
        live = ttk.Labelframe(t, text="Right now", style="Card.TLabelframe")
        live.pack(fill="x")
        self.pw_live = ttk.Label(live, text="", font=("DejaVu Sans Mono", 10), justify="left")
        self.pw_live.pack(anchor="w", side="left")
        self.info_btn(live, "throttle").pack(side="right", anchor="n")

        gr = ttk.Labelframe(t, text="Power draw - last 24 hours", style="Card.TLabelframe")
        gr.pack(fill="x", pady=(10, 0))
        self.pg = tk.Canvas(gr, height=190, bg="#ffffff", highlightthickness=1,
                            highlightbackground="#d1d5db")
        self.pg.pack(fill="x")
        self.pg.bind("<Configure>", lambda e: self.draw_power_graph())
        r = ttk.Frame(gr); r.pack(fill="x", pady=(6, 0))
        self.pg_avg = ttk.Label(r, text="", style="Ok.TLabel")
        self.pg_avg.pack(side="left")
        self.info_btn(r, "powergraph").pack(side="right")
        r = ttk.Frame(gr); r.pack(fill="x", pady=(4, 0))
        ttk.Label(r, text="Electric rate $/kWh:").pack(side="left")
        self.v_rate = tk.StringVar(value=str(self.s.get("rate", 0.19)))
        e = ttk.Entry(r, textvariable=self.v_rate, width=7)
        e.pack(side="left", padx=6)
        e.bind("<KeyRelease>", lambda ev: self.draw_power_graph())
        self.pg_cost = ttk.Label(r, text="", style="Dim.TLabel")
        self.pg_cost.pack(side="left", padx=6)
        self.pg_btn = ttk.Button(r, text="Start power logger", command=self.start_logger)
        self.pg_btn.pack(side="right")

        box = ttk.Labelframe(t, text="CPU & graphics profile", style="Card.TLabelframe")
        box.pack(fill="x", pady=(10, 0))
        top = ttk.Frame(box); top.pack(fill="x")
        ttk.Label(top, text="Pick one, then press Apply:", style="Dim.TLabel").pack(side="left")
        self.info_btn(top, "profile").pack(side="right")
        self.v_profile = tk.StringVar(value=self.s.get("profile", "normal"))
        for key, p in PROFILES.items():
            r = ttk.Frame(box); r.pack(fill="x", pady=2)
            ttk.Radiobutton(r, text=p["name"], value=key, variable=self.v_profile, width=14).pack(side="left")
            ttk.Label(r, text=p["desc"], style="Dim.TLabel", wraplength=560, justify="left").pack(side="left")
        r = ttk.Frame(box); r.pack(fill="x", pady=(6, 0))
        self.v_oc = tk.BooleanVar(value=self.s.get("overclock", False))
        ttk.Checkbutton(r, text="Overclock with Performance (CPU 2.8 GHz, GPU 1 GHz)",
                        variable=self.v_oc).pack(side="left")
        self.info_btn(r, "overclock").pack(side="right")
        r = ttk.Frame(box); r.pack(fill="x", pady=(8, 0))
        ttk.Button(r, text="Apply", style="Accent.TButton", command=self.apply_profile).pack(side="left")
        self.pw_note = ttk.Label(r, text="", style="Dim.TLabel")
        self.pw_note.pack(side="left", padx=10)

        pw = ttk.Labelframe(t, text="Restart / shut down", style="Card.TLabelframe")
        pw.pack(fill="x", pady=(10, 0))
        r = ttk.Frame(pw); r.pack(fill="x")
        ttk.Button(r, text="Restart", command=lambda: self.power("reboot")).pack(side="left")
        ttk.Button(r, text="Shut down", command=lambda: self.power("poweroff")).pack(side="left", padx=6)
        self.info_btn(r, "power").pack(side="right")
        self.power_tick()

    def power_tick(self):
        pol = "/sys/devices/system/cpu/cpufreq/policy0"
        gov = read_sys(pol + "/scaling_governor", "?")
        cur = read_sys(pol + "/scaling_cur_freq")
        mx = read_sys(pol + "/cpuinfo_max_freq")
        arm = vc("measure_clock", "arm")
        arm_mhz = int(arm.split("=")[1]) // 1_000_000 if "=" in arm else (int(cur) // 1000 if cur else 0)
        v3d = vc("measure_clock", "v3d")
        v3d_mhz = int(v3d.split("=")[1]) // 1_000_000 if "=" in v3d else None
        temp = vc("measure_temp").replace("temp=", "").replace("'C", " C")
        if not temp:
            t = read_sys("/sys/class/thermal/thermal_zone0/temp")
            temp = f"{int(t) / 1000:.1f} C" if t else "?"
        thr = vc("get_throttled")
        flags = []
        if "=" in thr:
            v = int(thr.split("=")[1], 16)
            if v & 0x1: flags.append("UNDER-VOLTAGE now")
            if v & 0x4: flags.append("THROTTLED now")
            if v & 0x8: flags.append("too hot now")
            if v & 0x10000 and not v & 0x1: flags.append("under-voltage since boot")
            if v & 0x40000 and not v & 0x4: flags.append("throttled since boot")
        lines = [f"CPU   {arm_mhz:>5} MHz   (max {int(mx) // 1000 if mx else '?'} MHz)   governor: {gov}",
                 f"GPU   {str(v3d_mhz) + ' MHz' if v3d_mhz else 'n/a':>9}",
                 f"Temp  {temp:>9}",
                 f"Draw  {(f'{w:.2f} W') if (w := pmic_watts()) is not None else 'n/a':>9}",
                 "Power " + ("✔ OK" if not flags and thr else ", ".join(flags) if flags else "n/a (vcgencmd not found)")]
        self.pw_live.config(text="\n".join(lines))
        self._pt = getattr(self, "_pt", 0) + 1
        if self._pt % 30 == 1:  # graph once a minute
            self.draw_power_graph()
        self.after(2000, self.power_tick)

    def logger_running(self):
        return run(["systemctl", "is-active", "pi-powerlog"])[1] == "active"

    def start_logger(self):
        src = os.path.join(os.path.dirname(os.path.realpath(__file__)), "pi-powerlog")
        if not os.path.exists("/usr/local/sbin/pi-powerlog"):
            if not os.path.exists(src):
                messagebox.showerror(APP_NAME, "pi-powerlog not found - re-run install.sh.")
                return
            self.root_cmd.run(["install", "-m", "0755", src, "/usr/local/sbin/pi-powerlog"])
            unit = src + ".service"
            if os.path.exists(unit):
                self.root_cmd.run(["install", "-m", "0644", unit, "/etc/systemd/system/pi-powerlog.service"])
            self.root_cmd.run(["systemctl", "daemon-reload"])
        rc, out = self.root_cmd.run(["systemctl", "enable", "--now", "pi-powerlog"])
        self._done(rc, out, "Power logger running - the graph fills in over the next 24 hours.")
        self.draw_power_graph()

    def draw_power_graph(self):
        c = self.pg
        c.delete("all")
        W, H = max(c.winfo_width(), 300), int(c.cget("height"))
        L, R, T, B = 44, 10, 10, 22
        pts = power_history(24)
        now = time.time()
        running = self.logger_running()
        self.pg_btn.pack_forget() if running else self.pg_btn.pack(side="right")
        if len(pts) < 2:
            c.create_text(W / 2, H / 2, fill="#6b7280",
                          text=("Collecting data… first points show up in a few minutes."
                                if running else "No data yet - press 'Start power logger'."))
            self.pg_avg.config(text="")
            self.pg_cost.config(text="")
            return
        ws = [w for _, w in pts]
        hi = max(ws) * 1.15 or 1
        hi = max(1, (int(hi) + 1))
        x = lambda t: L + (t - (now - 86400)) / 86400 * (W - L - R)
        y = lambda w: T + (1 - w / hi) * (H - T - B)
        # grid
        for i in range(0, 5):
            wv = hi * i / 4
            c.create_line(L, y(wv), W - R, y(wv), fill="#eef0f3")
            c.create_text(L - 6, y(wv), text=f"{wv:.1f}W", anchor="e", fill="#6b7280", font=("DejaVu Sans", 8))
        for h in range(0, 25, 6):
            tx = now - 86400 + h * 3600
            c.create_line(x(tx), T, x(tx), H - B, fill="#eef0f3")
            lbl = "now" if h == 24 else time.strftime("%I %p", time.localtime(tx)).lstrip("0")
            c.create_text(x(tx), H - B + 11, text=lbl, fill="#6b7280", font=("DejaVu Sans", 8),
                          anchor="e" if h == 24 else "center")
        # area + line (gaps > 5 min break the line)
        seg = []
        segs = [seg]
        for (t0, w0), (t1, _) in zip(pts, pts[1:] + [pts[-1]]):
            seg.append((x(t0), y(w0)))
            if t1 - t0 > 300:
                seg = []
                segs.append(seg)
        for sg in segs:
            if len(sg) >= 2:
                poly = [sg[0][0], y(0)] + [v for p in sg for v in p] + [sg[-1][0], y(0)]
                c.create_polygon(poly, fill="#fbe3ea", outline="")
                c.create_line([v for p in sg for v in p], fill="#c51a4a", width=2)
        # average (time-weighted is ~ the plain mean at a steady 1/min)
        avg = sum(ws) / len(ws)
        c.create_line(L, y(avg), W - R, y(avg), fill="#1d2430", dash=(4, 3))
        tid = c.create_text(L + 6, y(avg) - 9, text=f"avg {avg:.2f} W", anchor="w",
                            fill="#1d2430", font=("DejaVu Sans", 8, "bold"))
        bb = c.bbox(tid)
        c.tag_lower(c.create_rectangle(bb[0] - 3, bb[1] - 1, bb[2] + 3, bb[3] + 1,
                                       fill="#ffffff", outline="#d1d5db"), tid)
        span_h = (pts[-1][0] - pts[0][0]) / 3600
        kwh_day = avg * 24 / 1000
        self.pg_avg.config(text=f"Average {avg:.2f} W   ·   min {min(ws):.2f} W   ·   peak {max(ws):.2f} W"
                                f"   ·   ≈ {kwh_day:.3f} kWh/day" + (f"   ({span_h:.1f} h of data)" if span_h < 23.5 else ""))
        try:
            rate = float(self.v_rate.get())
            self.s["rate"] = rate
            save_settings(self.s)
            self.pg_cost.config(text=f"≈ ${kwh_day * rate * 30:.2f}/month   ·   ${kwh_day * rate * 365:.2f}/year")
        except ValueError:
            self.pg_cost.config(text="")

    def _boot_text(self, path):
        try:
            return open(path).read()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Can't read {path}:\n{e}")
            return None

    def _boot_write(self, path, text):
        self.root_cmd.run(["cp", "-n", path, path + ".bak-security"])
        with tempfile.NamedTemporaryFile("w", delete=False) as tf:
            tf.write(text)
        rc, out = self.root_cmd.run(["cp", tf.name, path])
        os.unlink(tf.name)
        return rc, out

    def config_block(self, name, lines):
        """Put lines in a marked block in config.txt (under [all]); [] removes the block.
        Returns True if the file changed."""
        txt = self._boot_text(CONFIG_TXT)
        if txt is None:
            return False
        b, e = f"# >>> pi-security {name} >>>", f"# <<< pi-security {name} <<<"
        new = re.sub(re.escape(b) + r".*?" + re.escape(e) + r"\n?", "", txt, flags=re.S)
        if lines:
            if not new.endswith("\n"):
                new += "\n"
            new += "\n".join([b, "[all]", *lines, e]) + "\n"
        if new == txt:
            return False
        rc, out = self._boot_write(CONFIG_TXT, new)
        if rc != 0:
            messagebox.showerror(APP_NAME, out)
            return False
        return True

    def cmdline_flag(self, token, on):
        """Add/remove one kernel option in cmdline.txt (a single line). Returns True if changed."""
        txt = self._boot_text(CMDLINE_TXT)
        if txt is None:
            return False
        key = token.split("=")[0]
        parts = [x for x in txt.split() if x.split("=")[0] != key]
        if on:
            parts.append(token)
        new = " ".join(parts) + "\n"
        if new.split() == txt.split():
            return False
        rc, out = self._boot_write(CMDLINE_TXT, new)
        if rc != 0:
            messagebox.showerror(APP_NAME, out)
            return False
        return True

    def ensure_power_service(self):
        """Boot-time helper that re-applies the CPU governor and NVMe read-ahead."""
        helper = f"""#!/bin/sh
# Installed by the Security app - re-applies CPU profile and NVMe read-ahead at boot.
G=$(cat {POWER_STATE}/governor 2>/dev/null)
if [ -n "$G" ]; then
  for p in /sys/devices/system/cpu/cpufreq/policy*; do echo "$G" > "$p/scaling_governor" 2>/dev/null; done
fi
RA=$(cat {POWER_STATE}/nvme-readahead 2>/dev/null)
if [ -n "$RA" ]; then
  for d in /sys/block/nvme*n*; do [ -e "$d/queue/read_ahead_kb" ] && echo "$RA" > "$d/queue/read_ahead_kb"; done
fi
exit 0
"""
        unit = f"""[Unit]
Description=Security app - CPU profile and NVMe tuning
After=local-fs.target

[Service]
Type=oneshot
ExecStart={POWER_HELPER}

[Install]
WantedBy=multi-user.target
"""
        self.root_cmd.run(["mkdir", "-p", POWER_STATE])
        self.root_cmd.write_file(POWER_HELPER, helper, "0755")
        self.root_cmd.write_file(POWER_UNIT, unit, "0644")
        self.root_cmd.run(["systemctl", "daemon-reload"])
        self.root_cmd.run(["systemctl", "enable", "pi-security-power.service"])

    def set_state(self, name, value):
        self.root_cmd.run(["mkdir", "-p", POWER_STATE])
        if value is None:
            return self.root_cmd.run(["rm", "-f", os.path.join(POWER_STATE, name)])
        return self.root_cmd.write_file(os.path.join(POWER_STATE, name), str(value) + "\n", "0644")

    def apply_profile(self):
        key = self.v_profile.get()
        p = PROFILES[key]
        oc = self.v_oc.get() and key == "perf"
        if oc and not messagebox.askyesno(APP_NAME, INFO["overclock"] + "\n\nOverclock?"):
            return
        if not self.root_cmd.ensure():
            return
        avail = read_sys("/sys/devices/system/cpu/cpufreq/policy0/scaling_available_governors").split()
        gov = p["governor"] if (not avail or p["governor"] in avail) else ("schedutil" if "schedutil" in avail else avail[0])
        # live change, every CPU cluster
        for pol in sorted(os.listdir("/sys/devices/system/cpu/cpufreq")) if os.path.isdir("/sys/devices/system/cpu/cpufreq") else []:
            if pol.startswith("policy"):
                self.root_cmd.run(["sh", "-c", f"echo {gov} > /sys/devices/system/cpu/cpufreq/{pol}/scaling_governor"])
        self.set_state("governor", gov)
        self.ensure_power_service()
        lines = p["config"] + (OVERCLOCK if oc else [])
        if all(l.startswith("#") for l in lines):
            lines = []  # nothing but comments - leave config.txt alone
        changed = self.config_block("power", lines)
        self.s.update(profile=key, overclock=oc)
        save_settings(self.s)
        msg = f"{p['name']} profile on (CPU governor: {gov})."
        if changed:
            msg += " Reboot to apply the GPU / overclock part."
            self.pw_note.config(text="Reboot needed for the config.txt part")
        else:
            self.pw_note.config(text="")
        self.say(msg)

    # ================================================================ TURBO DISK
    def build_disk(self):
        t = self.tab_disk
        st = ttk.Labelframe(t, text="Your NVMe drives", style="Card.TLabelframe")
        st.pack(fill="x")
        self.disk_info = ttk.Label(st, text="", font=("DejaVu Sans Mono", 10), justify="left")
        self.disk_info.pack(anchor="w")

        tb = ttk.Labelframe(t, text="Turbo Disk", style="Card.TLabelframe")
        tb.pack(fill="x", pady=(10, 0))
        r = ttk.Frame(tb); r.pack(fill="x")
        ttk.Button(r, text="⚡ TURBO ON (full speed)", style="Accent.TButton",
                   command=lambda: self.turbo(True)).pack(side="left")
        ttk.Button(r, text="Turbo OFF (stock)", command=lambda: self.turbo(False)).pack(side="left", padx=6)
        ttk.Label(tb, text="Turbo ON = all of the options below. Or set them one at a time:",
                  style="Dim.TLabel").pack(anchor="w", pady=(6, 4))

        self.v_gen3 = tk.BooleanVar(value=self.gen3_on())
        self.v_apst = tk.BooleanVar(value=self.cmd_has("nvme_core.default_ps_max_latency_us"))
        self.v_aspm = tk.BooleanVar(value=self.cmd_has("pcie_aspm"))
        ra = read_sys(POWER_STATE + "/nvme-readahead")
        self.v_ra = tk.StringVar(value=ra or "128")
        self.v_trim = tk.BooleanVar(value=run(["systemctl", "is-enabled", "fstrim.timer"])[1] == "enabled")
        for var, text, key in ((self.v_gen3, "PCIe Gen 3 (about 2x faster)", "gen3"),
                               (self.v_apst, "Keep the drive awake (no deep power saving)", "apst"),
                               (self.v_aspm, "PCIe link power saving OFF", "aspm"),
                               (self.v_trim, "Weekly TRIM (keeps the SSD fast)", "trim")):
            r = ttk.Frame(tb); r.pack(fill="x", pady=1)
            ttk.Checkbutton(r, text=text, variable=var).pack(side="left")
            self.info_btn(r, key).pack(side="right")
        r = ttk.Frame(tb); r.pack(fill="x", pady=1)
        ttk.Label(r, text="Read-ahead (KB):").pack(side="left")
        ttk.Combobox(r, textvariable=self.v_ra, values=["128", "512", "1024", "2048", "4096"],
                     width=7).pack(side="left", padx=6)
        self.info_btn(r, "readahead").pack(side="right")
        r = ttk.Frame(tb); r.pack(fill="x", pady=(8, 0))
        ttk.Button(r, text="Apply", command=self.apply_disk).pack(side="left")
        self.disk_note = ttk.Label(r, text="", style="Dim.TLabel")
        self.disk_note.pack(side="left", padx=10)

        sp = ttk.Labelframe(t, text="Speed test", style="Card.TLabelframe")
        sp.pack(fill="x", pady=(10, 0))
        r = ttk.Frame(sp); r.pack(fill="x")
        ttk.Button(r, text="Test read speed", command=self.speed_test).pack(side="left")
        self.speed_lbl = ttk.Label(r, text="", style="Ok.TLabel")
        self.speed_lbl.pack(side="left", padx=10)
        self.info_btn(r, "speedtest").pack(side="right")
        self.refresh_disk()

    def cmd_has(self, key):
        return any(x.split("=")[0] == key for x in read_sys(CMDLINE_TXT).split())

    def gen3_on(self):
        return bool(re.search(r"^\s*dtparam=pciex1_gen=3", read_sys(CONFIG_TXT), flags=re.M))

    def refresh_disk(self):
        gens = {"2.5": "Gen 1", "5.0": "Gen 2", "8.0": "Gen 3", "16.0": "Gen 4"}
        lines = []
        for name, dev in nvme_devices():
            model = read_sys(f"/sys/class/nvme/{name}/model", "NVMe drive")
            spd = read_sys(os.path.join(dev, "current_link_speed"))
            mx = read_sys(os.path.join(dev, "max_link_speed"))
            w = read_sys(os.path.join(dev, "current_link_width"))
            g = gens.get(spd.split()[0], "?") if spd else "?"
            gm = gens.get(mx.split()[0], "?") if mx else "?"
            lines.append(f"{name}: {model[:34]}")
            lines.append(f"   link now: {g} x{w or '?'} ({spd or '?'})   drive supports: {gm}")
        if not lines:
            lines = ["No NVMe drive found."]
        ra = read_sys("/sys/block/nvme0n1/queue/read_ahead_kb")
        lines.append(f"Config: Gen 3 {'ON' if self.gen3_on() else 'off'} · "
                     f"stay awake {'ON' if self.cmd_has('nvme_core.default_ps_max_latency_us') else 'off'} · "
                     f"ASPM {'OFF' if self.cmd_has('pcie_aspm') else 'on'} · read-ahead {ra or '?'} KB")
        self.disk_info.config(text="\n".join(lines))

    def turbo(self, on):
        self.v_gen3.set(on); self.v_apst.set(on); self.v_aspm.set(on); self.v_trim.set(True)
        self.v_ra.set("2048" if on else "128")
        self.apply_disk()

    def apply_disk(self):
        try:
            ra = int(self.v_ra.get())
        except ValueError:
            messagebox.showerror(APP_NAME, "Read-ahead must be a number (KB).")
            return
        if self.v_gen3.get() and not self.gen3_on():
            if not messagebox.askyesno(APP_NAME, INFO["gen3"] + "\n\nTurn on PCIe Gen 3?"):
                self.v_gen3.set(False)
        if not self.root_cmd.ensure():
            return
        reboot = False
        reboot |= self.config_block("pcie", ["dtparam=pciex1", "dtparam=pciex1_gen=3"] if self.v_gen3.get() else [])
        reboot |= self.cmdline_flag("nvme_core.default_ps_max_latency_us=0", self.v_apst.get())
        reboot |= self.cmdline_flag("pcie_aspm=off", self.v_aspm.get())
        # read-ahead: live + kept at boot
        for d in os.listdir("/sys/block") if os.path.isdir("/sys/block") else []:
            if d.startswith("nvme"):
                self.root_cmd.run(["sh", "-c", f"echo {ra} > /sys/block/{d}/queue/read_ahead_kb"])
        self.set_state("nvme-readahead", ra if ra != 128 else None)
        self.ensure_power_service()
        self.root_cmd.run(["systemctl", "enable" if self.v_trim.get() else "disable", "--now", "fstrim.timer"])
        self.refresh_disk()
        if reboot:
            self.disk_note.config(text="Reboot to finish (boot files changed)")
            if messagebox.askyesno(APP_NAME, "Disk settings saved. Some need a reboot.\nRestart now?"):
                self.root_cmd.run(["systemctl", "reboot"])
        else:
            self.disk_note.config(text="")
        self.say("Disk settings applied.")

    def speed_test(self):
        devs = [d for d in (os.listdir("/sys/block") if os.path.isdir("/sys/block") else [])
                if re.fullmatch(r"nvme\d+n\d+", d)]
        if not devs:
            messagebox.showinfo(APP_NAME, "No NVMe drive found.")
            return
        if not self.root_cmd.ensure():
            return
        dev = "/dev/" + devs[0]
        result = {}

        def job():
            import time
            t0 = time.monotonic()
            rc, out = self.root_cmd.run(["dd", f"if={dev}", "of=/dev/null", "bs=4M", "count=256",
                                         "iflag=direct", "status=none"], timeout=120)
            result["secs"] = max(0.001, time.monotonic() - t0)
            return rc, out

        def done():
            if "secs" in result:
                self.speed_lbl.config(text=f"{dev}: about {1024 / result['secs']:.0f} MB/s read")
        self.speed_lbl.config(text="testing…")
        self.bg(job, f"Speed test done on {dev}.", "Reading 1 GB from the drive…", after=done)

    # ================================================================ ACCESS
    def build_access(self):
        t = self.tab_access
        box = ttk.Labelframe(t, text="Who can get in", style="Card.TLabelframe")
        box.pack(fill="x")
        self.access_rows = {}
        rows = [
            ("autologin", "Desktop auto-login (no password at boot)", self.set_autologin),
            ("ssh", "SSH remote login", lambda on: self.raspi_toggle("do_ssh", on, "SSH")),
            ("vnc", "VNC remote desktop", lambda on: self.raspi_toggle("do_vnc", on, "VNC")),
            ("ufw", "Firewall (ufw)", self.set_firewall),
        ]
        for key, label, fn in rows:
            r = ttk.Frame(box); r.pack(fill="x", pady=3)
            ttk.Label(r, text=label, width=38).pack(side="left")
            st = ttk.Label(r, text="…", width=12)
            st.pack(side="left")
            ttk.Button(r, text="ON", width=5, command=lambda f=fn: f(True)).pack(side="left", padx=(4, 2))
            ttk.Button(r, text="OFF", width=5, command=lambda f=fn: f(False)).pack(side="left")
            self.info_btn(r, key).pack(side="right")
            self.access_rows[key] = st
        ttk.Button(box, text="Refresh", command=self.refresh_access).pack(anchor="w", pady=(6, 0))

        lg = ttk.Labelframe(t, text="Login history", style="Card.TLabelframe")
        lg.pack(fill="x", pady=(10, 0))
        r = ttk.Frame(lg); r.pack(fill="x")
        ttk.Button(r, text="Show failed logins (7 days)", command=lambda: self.show_logins(True)).pack(side="left")
        ttk.Button(r, text="Show successful logins", command=lambda: self.show_logins(False)).pack(side="left", padx=6)
        self.info_btn(r, "fails").pack(side="right")

        up = ttk.Labelframe(t, text="Updates", style="Card.TLabelframe")
        up.pack(fill="x", pady=(10, 0))
        r = ttk.Frame(up); r.pack(fill="x")
        ttk.Button(r, text="Check for updates", command=self.check_updates).pack(side="left")
        ttk.Button(r, text="Install updates", command=self.install_updates).pack(side="left", padx=6)
        self.info_btn(r, "updates").pack(side="right")
        self.upd_status = ttk.Label(up, text="", style="Dim.TLabel")
        self.upd_status.pack(anchor="w", pady=(6, 0))
        self.refresh_access()

    def _set_row(self, key, on, good_when_on):
        lbl = self.access_rows[key]
        if on is None:
            lbl.config(text="unknown", style="Dim.TLabel")
        else:
            good = on == good_when_on
            lbl.config(text=("● ON" if on else "○ OFF"), style="Ok.TLabel" if good else "Bad.TLabel")

    def refresh_access(self):
        self._set_row("autologin", self.autologin_on(), False)
        self._set_row("ssh", run(["systemctl", "is-active", "ssh"])[1] == "active", True)
        vnc = any(run(["systemctl", "is-active", u])[1] == "active"
                  for u in ("wayvnc", "wayvnc-control", "vncserver-x11-serviced"))
        self._set_row("vnc", vnc, True)
        if have("ufw") or os.path.exists("/usr/sbin/ufw"):
            rc, out = run(["sudo", "-n", "ufw", "status"])
            self._set_row("ufw", ("Status: active" in out) if rc == 0 else None, True)
        else:
            self.access_rows["ufw"].config(text="not installed", style="Dim.TLabel")
        # SSH / VNC are only "bad" if you don't use them, so show them neutral
        for k in ("ssh", "vnc"):
            self.access_rows[k].config(style="TLabel")

    @staticmethod
    def autologin_on():
        for f in ["/etc/lightdm/lightdm.conf"] + [
                os.path.join("/etc/lightdm/lightdm.conf.d", x)
                for x in (os.listdir("/etc/lightdm/lightdm.conf.d")
                          if os.path.isdir("/etc/lightdm/lightdm.conf.d") else [])]:
            try:
                if re.search(r"^\s*autologin-user\s*=\s*\S+", open(f).read(), flags=re.M):
                    return True
            except Exception:
                pass
        try:  # greetd (newer images)
            return "initial_session" in open("/etc/greetd/config.toml").read()
        except Exception:
            pass
        if os.path.exists("/etc/lightdm") or os.path.exists("/etc/greetd"):
            return False
        return None

    def set_autologin(self, on):
        if not have("raspi-config"):
            messagebox.showerror(APP_NAME, "raspi-config not found (it comes with Raspberry Pi OS).")
            return
        cli = run(["systemctl", "get-default"])[1].strip() == "multi-user.target"
        # B1 console+login, B2 console autologin, B3 desktop+login, B4 desktop autologin
        mode = ("B2" if on else "B1") if cli else ("B4" if on else "B3")
        if not on:
            messagebox.showinfo(APP_NAME, "After this, the Pi asks for your password at every boot.\n"
                                          "Make sure you know it!")
        rc, out = self.root_cmd.run(raspi("do_boot_behaviour", mode))
        self._done(rc, out, f"Auto-login {'on' if on else 'off'} - takes effect at next boot.")
        self.after(500, self.refresh_access)

    def set_firewall(self, on):
        if not self.root_cmd.ensure():
            return
        def job():
            if not have("ufw") and not os.path.exists("/usr/sbin/ufw"):
                rc, out = self.root_cmd.run(["apt-get", "install", "-y", "ufw"], timeout=600)
                if rc != 0:
                    return rc, out
            if on:
                for rule in (["allow", "22/tcp"], ["allow", "5900/tcp"]):
                    self.root_cmd.run(["ufw", *rule])
                self.root_cmd.run(["ufw", "default", "deny", "incoming"])
                self.root_cmd.run(["ufw", "default", "allow", "outgoing"])
                return self.root_cmd.run(["ufw", "--force", "enable"])
            return self.root_cmd.run(["ufw", "disable"])
        self.bg(job, f"Firewall {'on (SSH and VNC still allowed)' if on else 'off'}.",
                "Setting up the firewall…", after=self.refresh_access)

    def bg(self, job, ok_msg, busy_msg, after=None, show_output=False):
        """Run job() in a thread so the window stays responsive."""
        import threading
        self.say(busy_msg)
        result = {}

        def work():
            result["r"] = job()

        th = threading.Thread(target=work, daemon=True)
        th.start()

        def poll():
            if th.is_alive():
                self.after(300, poll)
                return
            rc, out = result.get("r", (1, "failed"))
            if rc == 0:
                self.say(ok_msg)
                if show_output:
                    self.text_window(ok_msg, out)
            else:
                messagebox.showerror(APP_NAME, out[-1500:] or "Failed.")
                self.say("Failed.")
            if after:
                after()
        poll()

    def text_window(self, title, text):
        w = tk.Toplevel(self)
        w.title(title)
        w.geometry("760x420")
        tx = tk.Text(w, wrap="none", font=("DejaVu Sans Mono", 9))
        sb = ttk.Scrollbar(w, command=tx.yview)
        tx.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tx.pack(fill="both", expand=True)
        tx.insert("1.0", text or "(nothing found)")
        tx.config(state="disabled")

    def show_logins(self, failed):
        if not self.root_cmd.ensure():
            return
        if failed:
            pat = "Failed password|Invalid user|authentication failure|FAILED SU|incorrect password"
        else:
            pat = "Accepted (password|publickey)|session opened for user " + USER
        def job():
            rc, out = self.root_cmd.run(["journalctl", "--since", "-7d", "--no-pager", "-o", "short",
                                         "-g", pat], timeout=60)
            lines = out.splitlines()[-300:]
            if rc == 1 and "No entries" in out or not lines:
                return 0, "(nothing found in the last 7 days)"
            return 0, "\n".join(lines)
        title = "Failed logins - last 7 days" if failed else "Successful logins - last 7 days"
        self.bg(job, title, "Reading the system log…", show_output=True)

    def check_updates(self):
        if not self.root_cmd.ensure():
            return
        def job():
            rc, out = self.root_cmd.run(["apt-get", "update"], timeout=600)
            if rc != 0:
                return rc, out
            rc, out = run(["apt", "list", "--upgradable"], timeout=60)
            pk = [l for l in out.splitlines() if "/" in l]
            self._upd_count = len(pk)
            return 0, "\n".join(pk) or "Everything is up to date."

        def done():
            n = getattr(self, "_upd_count", None)
            if n is not None:
                self.upd_status.config(text=f"{n} update(s) available" if n else "✔ Everything is up to date")
        self.bg(job, "Update check done", "Checking for updates…", after=done, show_output=True)

    def install_updates(self):
        if not messagebox.askyesno(APP_NAME, "Install all available updates now?\nThis can take several minutes."):
            return
        if not self.root_cmd.ensure():
            return
        def job():
            self.root_cmd.run(["apt-get", "update"], timeout=600)
            return self.root_cmd.run(["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "-y",
                                      "full-upgrade"], timeout=3600)
        def done():
            self.upd_status.config(text="Updates installed. "
                                   + ("Reboot needed." if os.path.exists("/var/run/reboot-required") else ""))
        self.bg(job, "Updates installed.", "Installing updates… (the window stays usable)", after=done)

    # ================================================================ LOGIN ONCE
    def build_login(self):
        t = self.tab_login
        box = ttk.Labelframe(t, text="Save your login (encrypted keyring)", style="Card.TLabelframe")
        box.pack(fill="x")
        g = ttk.Frame(box); g.pack(fill="x")
        ttk.Label(g, text="Username").grid(row=0, column=0, sticky="w", pady=3)
        self.v_user = tk.StringVar(value=USER)
        ttk.Entry(g, textvariable=self.v_user, width=24, state="readonly").grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(g, text="Password").grid(row=1, column=0, sticky="w", pady=3)
        self.v_pw = tk.StringVar()
        ttk.Entry(g, textvariable=self.v_pw, show="•", width=24).grid(row=1, column=1, sticky="w", padx=8)
        self.info_btn(g, "keyring").grid(row=0, column=3, sticky="e")
        g.columnconfigure(2, weight=1)
        r = ttk.Frame(box); r.pack(fill="x", pady=(8, 0))
        ttk.Button(r, text="Save to keyring", style="Accent.TButton", command=self.save_cred).pack(side="left")
        ttk.Button(r, text="Forget", command=self.forget_cred).pack(side="left", padx=8)
        self.cred_status = ttk.Label(r, text="")
        self.cred_status.pack(side="right")

        box2 = ttk.Labelframe(t, text="Skip the password prompt for these admin commands",
                              style="Card.TLabelframe")
        box2.pack(fill="both", expand=True, pady=(10, 0))
        top = ttk.Frame(box2); top.pack(fill="x")
        ttk.Label(top, text="Your apps run these with sudo:", style="Dim.TLabel").pack(side="left")
        self.info_btn(top, "sudo").pack(side="right")
        self.v_presets = []
        for name, _ in SUDO_PRESETS:
            v = tk.BooleanVar(value=name in self.s["presets"])
            ttk.Checkbutton(box2, text=name, variable=v).pack(anchor="w")
            self.v_presets.append(v)
        r = ttk.Frame(box2); r.pack(fill="x", pady=(4, 2))
        ttk.Label(r, text="Other commands (full paths, comma-separated):").pack(side="left")
        self.v_custom = tk.StringVar(value=self.s["custom"])
        ttk.Entry(box2, textvariable=self.v_custom).pack(fill="x")

        r = ttk.Frame(box2); r.pack(fill="x", pady=(8, 0))
        self.v_full = tk.BooleanVar(value=self.s["fullsudo"])
        ttk.Checkbutton(r, text="All sudo commands (no password ever)", variable=self.v_full).pack(side="left")
        self.info_btn(r, "fullsudo").pack(side="right")
        r = ttk.Frame(box2); r.pack(fill="x")
        self.v_polkit = tk.BooleanVar(value=self.s["polkit"])
        ttk.Checkbutton(r, text="Also skip the graphical admin pop-up (polkit)",
                        variable=self.v_polkit).pack(side="left")
        self.info_btn(r, "polkit").pack(side="right")

        r = ttk.Frame(box2); r.pack(fill="x", pady=(10, 0))
        ttk.Button(r, text="Apply", style="Accent.TButton", command=self.apply_sudo).pack(side="left")
        ttk.Button(r, text="Remove all", command=self.remove_sudo).pack(side="left", padx=8)
        self.sudo_status = ttk.Label(r, text="")
        self.sudo_status.pack(side="right")
        self.refresh_login_status()

    def refresh_login_status(self):
        if not have("secret-tool"):
            self.cred_status.config(text="keyring tools not installed", style="Bad.TLabel")
        elif keyring_get():
            self.cred_status.config(text="✔ saved in keyring", style="Ok.TLabel")
        else:
            self.cred_status.config(text="not saved", style="Dim.TLabel")
        rc, out = run(["sudo", "-n", "-l"])
        if rc == 0 and "NOPASSWD: ALL" in out:
            self.sudo_status.config(text="sudo never asks for a password", style="Ok.TLabel")
        elif os.path.exists(SUDOERS_FILE):
            self.sudo_status.config(text="✔ rules installed", style="Ok.TLabel")
        else:
            self.sudo_status.config(text="no rules installed", style="Dim.TLabel")

    def save_cred(self):
        pw = self.v_pw.get()
        if not pw:
            messagebox.showwarning(APP_NAME, "Type your password first.")
            return
        if not have("secret-tool"):
            messagebox.showerror(APP_NAME, "secret-tool is missing. On the Auto-Lock tab press "
                                           "'Install lock tools' (it also installs the keyring).")
            return
        if not Root._check(pw):
            messagebox.showerror(APP_NAME, "That password is wrong - sudo rejected it.")
            return
        rc, out = run(["secret-tool", "store", f"--label=Pi Security login ({USER})", *KEYRING_ATTRS],
                      inp=pw)
        self.v_pw.set("")
        if rc == 0:
            self.root_cmd.cached = pw
            self.say("Password verified and saved to the login keyring.")
        else:
            messagebox.showerror(APP_NAME, "Could not save to the keyring:\n" + out +
                                 "\n\nLog out and back in once after installing gnome-keyring.")
        self.refresh_login_status()

    def forget_cred(self):
        run(["secret-tool", "clear", *KEYRING_ATTRS])
        self.root_cmd.cached = None
        self.say("Saved password removed from the keyring.")
        self.refresh_login_status()

    def apply_sudo(self):
        chosen = [n for (n, _), v in zip(SUDO_PRESETS, self.v_presets) if v.get()]
        custom = [c.strip() for c in self.v_custom.get().split(",") if c.strip()]
        for c in custom:
            if not c.startswith("/") or not os.path.exists(c.split()[0]):
                messagebox.showerror(APP_NAME, f"'{c}' must be a full path that exists, e.g. /usr/bin/foo")
                return
        cmds = []
        for (n, paths) in SUDO_PRESETS:
            if n in chosen:
                cmds += [p for p in paths if os.path.exists(p)]
        cmds += custom
        full = self.v_full.get()
        if full and not messagebox.askyesno(APP_NAME, "Allow EVERY sudo command without a password?\n\n" + INFO["fullsudo"]):
            return
        self.s.update(presets=chosen, custom=", ".join(custom), fullsudo=full, polkit=self.v_polkit.get())
        save_settings(self.s)

        if not cmds and not full:
            self.remove_sudo(quiet=True)
        else:
            body = f"# Managed by the Security app - edit with the app, not by hand.\n"
            if full:
                body += f"{USER} ALL=(ALL) NOPASSWD: ALL\n"
            else:
                body += f"{USER} ALL=(root) NOPASSWD: " + ", ".join(sorted(set(cmds))) + "\n"
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".sudoers") as tf:
                tf.write(body)
                tmp = tf.name
            rc, out = run(["/usr/sbin/visudo", "-cf", tmp])
            if rc != 0:
                rc, out = self.root_cmd.run(["/usr/sbin/visudo", "-cf", tmp])
            os.unlink(tmp)
            if rc != 0:
                messagebox.showerror(APP_NAME, "Rule check failed, nothing changed:\n" + out)
                return
            rc, out = self.root_cmd.write_file(SUDOERS_FILE, body, "0440")
            if rc != 0:
                messagebox.showerror(APP_NAME, out)
                return

        if self.v_polkit.get():
            rule = ("// Managed by the Security app\n"
                    "polkit.addRule(function(action, subject) {\n"
                    f"  if (subject.user == \"{USER}\" && subject.local && subject.active) {{\n"
                    "    return polkit.Result.YES;\n  }\n});\n")
            self.root_cmd.write_file(POLKIT_FILE, rule, "0644")
        else:
            self.root_cmd.run(["rm", "-f", POLKIT_FILE])
        self.say("Sudo rules applied.")
        self.refresh_login_status()

    def remove_sudo(self, quiet=False):
        self.root_cmd.run(["rm", "-f", SUDOERS_FILE, POLKIT_FILE])
        if not quiet:
            for v in self.v_presets:
                v.set(False)
            self.v_full.set(False)
            self.v_polkit.set(False)
            self.s.update(presets=[], fullsudo=False, polkit=False)
            save_settings(self.s)
            self.say("Removed the Security app's sudo and polkit rules.")
        self.refresh_login_status()

    # ================================================================ CLOCK
    def build_clock(self):
        t = self.tab_clock
        top = ttk.Frame(t); top.pack(fill="x")
        self.clock_lbl = ttk.Label(top, text="", style="Big.TLabel")
        self.clock_lbl.pack(anchor="w")
        self.clock_info = ttk.Label(top, text="", style="Dim.TLabel")
        self.clock_info.pack(anchor="w")

        tz = ttk.Labelframe(t, text="Time zone & network time", style="Card.TLabelframe")
        tz.pack(fill="x", pady=(10, 0))
        r = ttk.Frame(tz); r.pack(fill="x")
        zones = run(["timedatectl", "list-timezones"])[1].splitlines() or ["America/Detroit"]
        self.v_tz = tk.StringVar(value=self.current_tz())
        ttk.Combobox(r, textvariable=self.v_tz, values=zones, width=28).pack(side="left")
        ttk.Button(r, text="Set time zone", command=self.set_tz).pack(side="left", padx=6)
        r = ttk.Frame(tz); r.pack(fill="x", pady=(6, 0))
        ttk.Button(r, text="Network time ON", command=lambda: self.set_ntp(True)).pack(side="left")
        ttk.Button(r, text="Network time OFF", command=lambda: self.set_ntp(False)).pack(side="left", padx=6)
        ttk.Button(r, text="Sync now", command=self.sync_now).pack(side="left")
        self.info_btn(r, "ntp").pack(side="right")

        man = ttk.Labelframe(t, text="Set date & time by hand", style="Card.TLabelframe")
        man.pack(fill="x", pady=(10, 0))
        r = ttk.Frame(man); r.pack(fill="x")
        now = datetime.datetime.now()
        self.v_date = tk.StringVar(value=now.strftime("%Y-%m-%d"))
        self.v_time = tk.StringVar(value=now.strftime("%H:%M:%S"))
        ttk.Entry(r, textvariable=self.v_date, width=12).pack(side="left")
        ttk.Entry(r, textvariable=self.v_time, width=10).pack(side="left", padx=6)
        ttk.Button(r, text="Set", command=self.set_manual).pack(side="left")
        ttk.Button(r, text="Use now", command=self.fill_now).pack(side="left", padx=6)

        rtc = ttk.Labelframe(t, text="Pi 5 real-time clock (RTC)", style="Card.TLabelframe")
        rtc.pack(fill="x", pady=(10, 0))
        r = ttk.Frame(rtc); r.pack(fill="x")
        ttk.Button(r, text="Read RTC", command=self.read_rtc).pack(side="left")
        ttk.Button(r, text="Save to RTC", command=self.save_rtc).pack(side="left", padx=6)
        ttk.Button(r, text="Load from RTC", command=self.load_rtc).pack(side="left")
        self.info_btn(r, "rtc").pack(side="right")
        r = ttk.Frame(rtc); r.pack(fill="x", pady=(6, 0))
        ttk.Button(r, text="Battery charging ON", command=lambda: self.set_charge(True)).pack(side="left")
        ttk.Button(r, text="Battery charging OFF", command=lambda: self.set_charge(False)).pack(side="left", padx=6)
        self.info_btn(r, "charge").pack(side="right")

        pn = ttk.Labelframe(t, text="Taskbar clock", style="Card.TLabelframe")
        pn.pack(fill="x", pady=(10, 0))
        r = ttk.Frame(pn); r.pack(fill="x")
        ttk.Button(r, text="12-hour", command=lambda: self.set_panel("%I:%M %p")).pack(side="left")
        ttk.Button(r, text="24-hour", command=lambda: self.set_panel("%H:%M")).pack(side="left", padx=6)
        ttk.Button(r, text="With seconds", command=lambda: self.set_panel("%I:%M:%S %p")).pack(side="left")
        self.info_btn(r, "panel").pack(side="right")

    def current_tz(self):
        rc, out = run(["timedatectl", "show", "-p", "Timezone", "--value"])
        if rc == 0 and out:
            return out
        try:
            return open("/etc/timezone").read().strip()
        except Exception:
            return "America/Detroit"

    def tick(self):
        now = datetime.datetime.now().astimezone()
        self.clock_lbl.config(text=now.strftime("%a %b %d  %I:%M:%S %p"))
        if not hasattr(self, "_tick_n") or self._tick_n % 10 == 0:
            rc, out = run(["timedatectl", "show"])
            d = dict(l.split("=", 1) for l in out.splitlines() if "=" in l) if rc == 0 else {}
            ntp = "on" if d.get("NTP") == "yes" else "off"
            synced = "synced" if d.get("NTPSynchronized") == "yes" else "not synced"
            self.clock_info.config(text=f"{d.get('Timezone', now.tzname())}  ·  network time {ntp} "
                                        f"({synced})  ·  RTC {'present' if os.path.exists('/dev/rtc0') else 'not found'}")
        self._tick_n = getattr(self, "_tick_n", 0) + 1
        self.after(1000, self.tick)

    def _done(self, rc, out, ok):
        if rc == 0:
            self.say(ok)
        else:
            messagebox.showerror(APP_NAME, out or "Failed.")
        self._tick_n = 0

    def set_tz(self):
        self._done(*self.root_cmd.run(["timedatectl", "set-timezone", self.v_tz.get()]),
                   f"Time zone set to {self.v_tz.get()}.")

    def set_ntp(self, on):
        self._done(*self.root_cmd.run(["timedatectl", "set-ntp", "true" if on else "false"]),
                   f"Network time {'on' if on else 'off'}.")

    def sync_now(self):
        self._done(*self.root_cmd.run(["systemctl", "restart", "systemd-timesyncd"]),
                   "Asked the time server for a fresh sync.")

    def fill_now(self):
        now = datetime.datetime.now()
        self.v_date.set(now.strftime("%Y-%m-%d"))
        self.v_time.set(now.strftime("%H:%M:%S"))

    def set_manual(self):
        try:
            datetime.datetime.strptime(f"{self.v_date.get()} {self.v_time.get()}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            messagebox.showerror(APP_NAME, "Use YYYY-MM-DD and HH:MM:SS (24-hour).")
            return
        if run(["timedatectl", "show", "-p", "NTP", "--value"])[1] == "yes":
            if not messagebox.askyesno(APP_NAME, "Network time is on and would undo this.\nTurn it off and set the time?"):
                return
            self.root_cmd.run(["timedatectl", "set-ntp", "false"])
        self._done(*self.root_cmd.run(["timedatectl", "set-time", f"{self.v_date.get()} {self.v_time.get()}"]),
                   "Clock set.")

    def read_rtc(self):
        rc, out = self.root_cmd.run(["hwclock", "-r"])
        messagebox.showinfo(APP_NAME, "RTC time:\n" + out) if rc == 0 else messagebox.showerror(APP_NAME, out)

    def save_rtc(self):
        self._done(*self.root_cmd.run(["hwclock", "-w"]), "System time saved to the RTC.")

    def load_rtc(self):
        self._done(*self.root_cmd.run(["hwclock", "-s"]), "System time loaded from the RTC.")

    def set_charge(self, on):
        cfg = "/boot/firmware/config.txt" if os.path.exists("/boot/firmware/config.txt") else "/boot/config.txt"
        if on and not messagebox.askyesno(APP_NAME, INFO["charge"] + "\n\nEnable charging?"):
            return
        try:
            txt = open(cfg).read()
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))
            return
        txt = re.sub(r"^dtparam=rtc_bbat_vchg=.*\n?", "", txt, flags=re.M)
        if on:
            if not txt.endswith("\n"):
                txt += "\n"
            txt += "dtparam=rtc_bbat_vchg=3000000\n"
        self.root_cmd.run(["cp", cfg, cfg + ".bak-security"])
        with tempfile.NamedTemporaryFile("w", delete=False) as tf:
            tf.write(txt)
        rc, out = self.root_cmd.run(["cp", tf.name, cfg])
        os.unlink(tf.name)
        self._done(rc, out,
                   f"RTC battery charging {'on' if on else 'off'} - reboot to apply (backup: {cfg}.bak-security).")

    def set_panel(self, fmt):
        try:
            txt = open(PANEL_INI).read()
        except FileNotFoundError:
            txt = ""
        if re.search(r"^clock_time_format=", txt, flags=re.M):
            txt = re.sub(r"^clock_time_format=.*$", f"clock_time_format={fmt}", txt, flags=re.M)
        else:
            if "[panel]" not in txt:
                txt = "[panel]\n" + txt
            txt = txt.replace("[panel]", f"[panel]\nclock_time_format={fmt}", 1)
        with open(PANEL_INI, "w") as f:
            f.write(txt)
        self.say("Taskbar clock format saved - it updates in a few seconds.")


if __name__ == "__main__":
    App().mainloop()
