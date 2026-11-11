#!/usr/bin/env python3
"""
Security - auto-lock, log-in-once and clock settings for Raspberry Pi 5.

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
import tkinter as tk
from tkinter import messagebox, ttk

APP_NAME = "Security"
VERSION = "1.2.0"
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
        self.geometry("720x800")
        self.minsize(560, 420)
        self.s = load_settings()
        self.root_cmd = Root(self)
        self._style()

        head = ttk.Frame(self, padding=(16, 12, 16, 4))
        head.pack(fill="x")
        ttk.Label(head, text="\U0001F512  Security", style="H1.TLabel").pack(side="left")
        ttk.Label(head, text=f"v{VERSION} · {USER} · {session_type()}",
                  style="Dim.TLabel").pack(side="right")

        self.nb = nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(4, 0))
        pages = []
        for name in ("  Auto-Lock  ", "  Sleep & Power  ", "  Access  ", "  Login Once  ", "  Clock  "):
            outer, inner = self._scroller(nb)
            nb.add(outer, text=name)
            pages.append(inner)
        self.tab_lock, self.tab_power, self.tab_access, self.tab_login, self.tab_clock = pages

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status, style="Status.TLabel",
                  anchor="w", padding=(14, 6)).pack(fill="x", side="bottom")

        self.build_lock()
        self.build_power()
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
    def build_power(self):
        t = self.tab_power
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

        pw = ttk.Labelframe(t, text="Power", style="Card.TLabelframe")
        pw.pack(fill="x", pady=(10, 0))
        r = ttk.Frame(pw); r.pack(fill="x")
        ttk.Button(r, text="Restart", command=lambda: self.power("reboot")).pack(side="left")
        ttk.Button(r, text="Shut down", command=lambda: self.power("poweroff")).pack(side="left", padx=6)
        self.info_btn(r, "power").pack(side="right")
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
