#!/usr/bin/env python3
"""Hamza GSM Tool v7 -- professional servicing toolkit GUI with login system.

Run:  python app.py
Requires Google platform-tools (adb/fastboot) on PATH or in ./platform-tools/

v7: Drivers tab (driver check/install + official links), Test Point / EDL tab
(per-brand safe key methods + model search), Backup tab (APK + device report),
Publish Update tab (one-click release builder -> GitHub), Save/Clear log.
v6: self-hosted updates. v5: update framework. v4: login system.
All servicing logic still comes from features.py.
"""

# ---- startup stage logger: sab se pehle, tkinter se bhi pehle ----
# Agar exe foran band ho jaye to startup.log me pata chalta hai ke
# code kahan tak pahuncha. Ye logger kabhi crash nahi karta.
import os as _os
import sys as _sys


def _stage(msg):
    try:
        if getattr(_sys, "frozen", False):
            _base = _os.path.dirname(_os.path.abspath(_sys.executable))
        else:
            _base = _os.path.dirname(_os.path.abspath(__file__))
        with open(_os.path.join(_base, "startup.log"), "a",
                  encoding="utf-8") as _f:
            _f.write(msg + "\n")
    except Exception:
        pass


_stage("stage 1: python started")

import os
import queue
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext, ttk

import adbwrap
import backup_admin
import paths
import brands
import lockedhelp
import recovery
import drivers
import edl
import features
import iphone
import models
import release
import updater
import users
from version import __version__

APP_TITLE = f"Hamza GSM Tool v{__version__}"


def _install_crash_handler():
    """Frozen exe (--windowed) me exception khamoshi se band kar deta hai.

    Is liye crash ki poori detail error.log me likho aur ek popup bhi
    dikhao taake user screenshot bhej sake.
    """
    import sys
    import traceback

    def hook(etype, value, tb):
        msg = "".join(traceback.format_exception(etype, value, tb))
        try:
            with open(os.path.join(paths.base_dir(), "error.log"),
                      "w", encoding="utf-8") as f:
                f.write(msg)
        except Exception:
            pass
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Hamza GSM Tool -- Error",
                "Tool khulne me error aaya. Ye detail ka screenshot bhejo:\n\n"
                + msg[-1500:])
            root.destroy()
        except Exception:
            pass

    sys.excepthook = hook


_install_crash_handler()
_stage("stage 3: imports + crash handler ok")

# Local accounts database, next to this script. Created on first run.
USERS_DB = os.path.join(paths.base_dir(), "users.db")

# ------------------------------- theme -------------------------------
BG = "#1e1e2e"        # dark slate
PANEL = "#2a2a3e"
CARD = "#31314a"
FG = "#e8e8f0"
MUTED = "#a0a0b8"
ACCENT = "#7c6cf0"    # purple
TEAL = "#00d4aa"
DANGER = "#ff5c5c"
WARN_BG = "#4a2a2a"

# Brand tiles: (key, badge text, display name, tile color, text color).
# ORIGINAL badge artwork -- initials only, not official logos.
BRAND_TILES = [
    ("samsung", "S", "Samsung", "#1428A0", "#ffffff"),
    ("xiaomi", "Mi", "Xiaomi", "#FF6900", "#ffffff"),
    ("tecno", "T", "Tecno", "#0A84FF", "#ffffff"),
    ("infinix", "i", "Infinix", "#00B140", "#ffffff"),
    ("itel", "itel", "itel", "#D7263D", "#ffffff"),
    ("oppo", "O", "Oppo", "#01996B", "#ffffff"),
    ("vivo", "V", "Vivo", "#4D7CFE", "#ffffff"),
    ("realme", "R", "Realme", "#FFC300", "#1e1e2e"),
    ("motorola", "M", "Motorola", "#2E5BFF", "#ffffff"),
    ("nokia", "N", "Nokia", "#005AFF", "#ffffff"),
    ("oneplus", "1+", "OnePlus", "#EB0028", "#ffffff"),
    ("huawei", "H", "Huawei", "#C7000B", "#ffffff"),
    ("qmobile", "Q", "QMobile", "#00B8A9", "#ffffff"),
    ("apple", "iP", "iPhone", "#333333", "#ffffff"),
]
TILE_W, TILE_H, TILE_PAD, TILE_COLS = 168, 104, 18, 4


def rounded_rect(cv, x1, y1, x2, y2, r, **kwargs):
    """Rounded rectangle on a Canvas (Tk has no native one)."""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
           x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kwargs)


class ToolApp(tk.Tk):
    def __init__(self):
        super().__init__()
        _stage("stage 4: tk root created")
        self.withdraw()  # hidden until login succeeds
        self.title(APP_TITLE)
        self.geometry("1280x760")
        self.configure(bg=BG)
        self.adb = adbwrap.find_binary("adb")
        self.fb = adbwrap.find_binary("fastboot")
        self.serial = tk.StringVar()
        self.status_var = tk.StringVar()
        self._jobs = queue.Queue()
        self._brand_key = None
        self.current_user = None
        self.current_is_admin = False
        self.current_expiry = None
        self._users_tab_added = False
        self._build()
        _stage("stage 5: UI built")
        self._poll_jobs()
        self._update_status()
        self.log(f"adb: {self.adb or 'NOT FOUND'}")
        self.log(f"fastboot: {self.fb or 'NOT FOUND'}")
        if not self.adb or not self.fb:
            self.log("WARNING: install platform-tools (see README.md).")
        self._login_flow()  # modal; destroys app if cancelled

    # --------------------------- ui builders ---------------------------
    # ================= v8.0 PRO UI =================
    # Brand -> Mode -> Function -> START. Simple, like pro tools.
    PRO_MODES = [
        ("adb", "ADB"),
        ("fastboot", "FASTBOOT"),
        ("meta", "META"),
        ("brom", "EDL/BROM"),
        ("tools", "TOOLS"),
    ]

    PRO_FUNCTIONS = {
        "adb": [
            ("read_info", "[ADB] Read Info"),
            ("reboot_recovery", "[ADB] Reboot to Recovery"),
            ("reboot_fastboot", "[ADB] Reboot to Fastboot"),
            ("reboot_meta", "[ADB] Reboot to META"),
            ("mdm_fix", "[ADB] MDM Scan & Fix"),
            ("list_pkgs", "[ADB] List Packages"),
            ("backup_apk", "[ADB] Backup APKs"),
        ],
        "fastboot": [
            ("fb_check", "[FASTBOOT] Check Device"),
            ("fb_info", "[FASTBOOT] Read All Info"),
            ("frp_erase", "[FASTBOOT] Erase FRP"),
            ("frp_config", "[FASTBOOT] Erase Config (MTK)"),
            ("fb_unlock", "[FASTBOOT] Unlock Bootloader"),
            ("fb_lock", "[FASTBOOT] Relock Bootloader"),
            ("fb_reboot", "[FASTBOOT] Reboot System"),
        ],
        "meta": [
            ("meta_boot", "[META] Boot to META Mode"),
        ],
        "brom": [
            ("edl_guide", "[EDL] Test Point Guide"),
        ],
        "tools": [
            ("drivers", "[TOOLS] Install Drivers"),
            ("iphone", "[TOOLS] iPhone Tools"),
            ("backup", "[TOOLS] Backup / Restore"),
            ("guides", "[TOOLS] Guides"),
            ("users", "[TOOLS] Users (Admin)"),
            ("publish", "[TOOLS] Publish Update"),
        ],
    }

    def _build(self):
        """v8.0 Pro layout: Brand -> Mode -> Function -> START."""
        self._pro_state = {"brand": None, "mode": "adb", "func": None}
        self._pro_header()
        self._pro_brandbar()
        self._pro_modetabs()
        self._pro_main()
        self._pro_bottom()
        self._status_bar()
        self._pro_refresh_functions()
        self._pro_refresh_models()

    def _pro_header(self):
        head = tk.Frame(self, bg=ACCENT, height=58)
        head.pack(fill="x")
        head.pack_propagate(False)
        tk.Label(head, text=f"  HAMZA GSM TOOL  v{__version__}",
                 bg=ACCENT, fg="#ffffff",
                 font=("Arial", 18, "bold")).pack(side="left", pady=8)
        # connection indicators
        self.pro_adb_led = tk.Label(head, text="● ADB", bg=ACCENT, fg="#888888",
                                    font=("Arial", 10, "bold"))
        self.pro_adb_led.pack(side="left", padx=(30, 8))
        self.pro_fb_led = tk.Label(head, text="● FB", bg=ACCENT, fg="#888888",
                                   font=("Arial", 10, "bold"))
        self.pro_fb_led.pack(side="left", padx=8)
        self._btn(head, "⟳", self._pro_refresh_conn,
                  bg=CARD, fg=FG).pack(side="right", padx=4)
        self._btn(head, "Logout", self._logout,
                  bg=CARD, fg=FG).pack(side="right", padx=4)

    def _pro_refresh_conn(self):
        def job():
            adb_ok = False
            fb_ok = False
            try:
                if self.adb:
                    out = adbwrap.run(self.adb, ["devices"])
                    adb_ok = any("device" in l and "unauthorized" not in l
                                 for l in out.splitlines()[1:] if l.strip())
            except Exception:
                pass
            try:
                if self.fb:
                    fb_ok = bool(features.fastboot_devices(self.fb))
            except Exception:
                pass
            return adb_ok, fb_ok

        def done(res):
            adb_ok, fb_ok = res
            self.pro_adb_led.config(fg="#00ff88" if adb_ok else "#888888")
            self.pro_fb_led.config(fg="#00ff88" if fb_ok else "#888888")
            self.log(f"Conn: ADB={'OK' if adb_ok else '--'}, "
                     f"Fastboot={'OK' if fb_ok else '--'}")
        self._run_bg_cb("conn check", job, done)

    def _pro_brandbar(self):
        bar = tk.Frame(self, bg=BG, pady=6)
        bar.pack(fill="x", padx=8)
        tk.Label(bar, text="Brand:", bg=BG, fg=MUTED,
                 font=("Arial", 10, "bold")).pack(side="left", padx=(0, 6))
        # scrollable brand buttons
        canvas = tk.Canvas(bar, bg=BG, highlightthickness=0, height=34)
        scr = tk.Scrollbar(bar, orient="horizontal", command=canvas.xview)
        inner = tk.Frame(canvas, bg=BG)
        canvas.configure(xscrollcommand=scr.set)
        canvas.pack(side="left", fill="x", expand=True)
        scr.pack(side="left", fill="x")
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        self._pro_brand_btns = {}
        for key, badge, name, color, fg in BRAND_TILES:
            b = tk.Button(inner, text=badge, bg=color, fg=fg,
                          font=("Arial", 9, "bold"), relief="flat",
                          padx=10, pady=6, cursor="hand2",
                          command=lambda k=key: self._pro_select_brand(k))
            b.pack(side="left", padx=3)
            self._pro_brand_btns[key] = b

    def _pro_select_brand(self, key):
        self._pro_state["brand"] = key
        for k, b in self._pro_brand_btns.items():
            b.config(relief="sunken" if k == key else "flat")
        name = next(t[2] for t in BRAND_TILES if t[0] == key)
        self.log(f"Brand: {name}")
        self._pro_refresh_models()

    def _pro_modetabs(self):
        bar = tk.Frame(self, bg=BG, pady=4)
        bar.pack(fill="x", padx=8)
        self._pro_mode_btns = {}
        for key, label in self.PRO_MODES:
            b = self._btn(bar, label,
                          lambda k=key: self._pro_select_mode(k),
                          bg=CARD, fg=FG)
            b.pack(side="left", padx=3)
            self._pro_mode_btns[key] = b
        self._pro_update_mode_btns()

    def _pro_select_mode(self, key):
        self._pro_state["mode"] = key
        self._pro_state["func"] = None
        self._pro_update_mode_btns()
        self._pro_refresh_functions()

    def _pro_update_mode_btns(self):
        cur = self._pro_state["mode"]
        for k, b in self._pro_mode_btns.items():
            b.config(bg=TEAL if k == cur else CARD,
                     fg="#ffffff" if k == cur else FG)

    def _pro_main(self):
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=8, pady=4)
        # left: models
        left = tk.Frame(main, bg=BG, width=280)
        left.pack(side="left", fill="y", padx=(0, 6))
        left.pack_propagate(False)
        tk.Label(left, text="Model (search):", bg=BG, fg=MUTED,
                 font=("Arial", 10, "bold")).pack(anchor="w")
        self.pro_search_var = tk.StringVar()
        se = tk.Entry(left, textvariable=self.pro_search_var, bg=PANEL, fg=FG,
                      insertbackground=FG, relief="flat", highlightthickness=1,
                      highlightbackground="#3a3a55", font=("Arial", 10))
        se.pack(fill="x", pady=4)
        self.pro_search_var.trace_add("write",
                                      lambda *_a: self._pro_refresh_models())
        self.pro_model_list = tk.Listbox(left, bg=PANEL, fg=FG,
                                         selectbackground=ACCENT, relief="flat",
                                         highlightthickness=1,
                                         highlightbackground="#3a3a55",
                                         font=("Arial", 10))
        self.pro_model_list.pack(fill="both", expand=True)
        # right: functions
        right = tk.Frame(main, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        tk.Label(right, text="Functions:", bg=BG, fg=MUTED,
                 font=("Arial", 10, "bold")).pack(anchor="w")
        self.pro_func_list = tk.Listbox(right, bg=PANEL, fg=FG,
                                        selectbackground=TEAL, relief="flat",
                                        highlightthickness=1,
                                        highlightbackground="#3a3a55",
                                        font=("Arial", 11))
        self.pro_func_list.pack(fill="both", expand=True, pady=4)
        self.pro_func_list.bind("<<ListboxSelect>>", self._pro_func_selected)
        self.pro_func_list.bind("<Double-Button-1>",
                                lambda _e: self._pro_start())
        # status line
        self.op_status = tk.Label(right, text="Function select karo, phir START dabao.",
                                  bg=BG, fg=MUTED, font=("Arial", 10),
                                  wraplength=700, justify="left")
        self.op_status.pack(anchor="w", pady=4)

    def _pro_refresh_models(self):
        q = (self.pro_search_var.get() or "").strip().lower()
        brand = self._pro_state["brand"]
        self.pro_model_list.delete(0, "end")
        if not brand:
            self.pro_model_list.insert("end", "(pehle upar se brand chuno)")
            return
        if brand == "apple":
            rows = models.search_models("apple", q)
        else:
            rows = models.search_models(brand, q)
        if not rows:
            self.pro_model_list.insert("end", "(koi model nahi mila)")
            return
        for m in rows[:200]:
            code = f" [{m['code']}]" if m.get("code") else ""
            self.pro_model_list.insert("end", f"{m['model']}{code}")

    def _pro_refresh_functions(self):
        mode = self._pro_state["mode"]
        self.pro_func_list.delete(0, "end")
        self._pro_func_ids = []
        for fid, label in self.PRO_FUNCTIONS.get(mode, []):
            self.pro_func_list.insert("end", label)
            self._pro_func_ids.append(fid)
        self.op_status.config(text="Function select karo, phir START dabao.",
                              fg=MUTED)

    def _pro_func_selected(self, _event=None):
        sel = self.pro_func_list.curselection()
        if sel:
            self._pro_state["func"] = self._pro_func_ids[sel[0]]
        else:
            self._pro_state["func"] = None

    def _pro_bottom(self):
        bar = tk.Frame(self, bg=BG, pady=8)
        bar.pack(fill="x", padx=8)
        self._btn(bar, "▶  START", self._pro_start,
                  bg=TEAL, fg="#ffffff").pack(side="left", padx=3,
                                              ipadx=30, ipady=6)
        self._btn(bar, "■ STOP", self._pro_stop,
                  bg=DANGER, fg="#ffffff").pack(side="left", padx=3,
                                                ipadx=10, ipady=6)
        # log area
        logf = tk.Frame(self, bg=BG)
        logf.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        tk.Label(logf, text="Log:", bg=BG, fg=MUTED,
                 font=("Arial", 10, "bold")).pack(anchor="w")
        self.log_text = scrolledtext.ScrolledText(logf, height=8, bg=PANEL,
                                                  fg=FG, relief="flat",
                                                  highlightthickness=1,
                                                  highlightbackground="#3a3a55",
                                                  font=("Arial", 9))
        self.log_text.pack(fill="both", expand=True)

    def _pro_stop(self):
        self.log("STOP dabaya gaya.")
        self.op_status.config(text="Rok diya gaya.", fg=WARN_BG)

    def _pro_start(self):
        fid = self._pro_state.get("func")
        if not fid:
            self.op_status.config(text="Pehle koi function select karo!",
                                  fg=DANGER)
            return
        self._pro_run_function(fid)

    # ============ function dispatcher ============
    def _pro_run_function(self, fid):
        """Selected function ko asal backend se chalao."""
        self.log(f">> {fid}")
        fn = self._pro_dispatch().get(fid)
        if not fn:
            self.op_status.config(text=f"Unknown function: {fid}", fg=DANGER)
            return
        fn()

    def _pro_dispatch(self):
        return {
            # ---- ADB ----
            "read_info": self.read_info,
            "reboot_recovery": lambda: self.reboot("recovery"),
            "reboot_fastboot": lambda: self.reboot("fastboot"),
            "reboot_meta": lambda: self.reboot("meta"),
            "mdm_fix": self._pro_mdm_fix,
            "list_pkgs": self._pro_list_pkgs,
            "backup_apk": self._pro_backup_apk,
            # ---- FASTBOOT ----
            "fb_check": self._pro_fb_check,
            "fb_info": self._pro_fb_info,
            "frp_erase": self._pro_frp_erase,
            "frp_config": self._pro_frp_config,
            "fb_unlock": self._pro_fb_unlock,
            "fb_lock": self._pro_fb_lock,
            "fb_reboot": self._pro_fb_reboot,
            # ---- META ----
            "meta_boot": lambda: self.reboot("meta"),
            # ---- EDL/BROM ----
            "edl_guide": self._pro_edl_guide,
            # ---- TOOLS ----
            "drivers": self._pro_drivers,
            "iphone": self._pro_iphone,
            "backup": self._pro_backup,
            "guides": self._pro_guides,
            "users": self._pro_users,
            "publish": self._pro_publish,
        }

    # ---- pro wrappers (sab self.op_status use karte hain) ----
    def _pro_set_status(self, text, color=None):
        self.op_status.config(text=text, fg=color or FG)
        self.log(text)

    def _pro_mdm_fix(self):
        """MDM Easy Fix: check -> scan -> fix, sab ek me."""
        self._pro_set_status("MDM Fix: device check ho raha hai...", TEAL)

        def job():
            if not self.adb:
                return "ERR: adb nahi mila"
            try:
                out = adbwrap.run(self.adb, ["devices"])
            except Exception as exc:
                return "ERR:" + str(exc)
            lines = [l for l in out.splitlines()[1:] if l.strip()]
            devs = [l for l in lines if "device" in l and "unauthorized" not in l]
            if not devs:
                return "ERR: phone nahi mila (USB debugging ON karo)"
            pkgs = features.list_packages(self.adb, self._serial())
            found = features.find_suspicious_packages(pkgs)
            if not found:
                return "OK: koi MDM app nahi mili -- phone saaf hai!"
            fixed = []
            for pkg in found:
                try:
                    features.disable_package(self.adb, pkg, self._serial())
                    fixed.append(pkg)
                except Exception as exc:
                    fixed.append(f"FAIL {pkg}: {exc}")
            return "OK: MDM fix ho gaya: " + ", ".join(fixed)

        def done(res):
            if res.startswith("OK:"):
                self._pro_set_status("✅ " + res[3:], TEAL)
            else:
                self._pro_set_status("❌ " + res[4:], DANGER)
        self._run_bg_cb("mdm fix", job, done)

    def _pro_list_pkgs(self):
        def job():
            pkgs = features.list_packages(self.adb, self._serial())
            return pkgs

        def done(pkgs):
            self._pro_set_status(f"✅ {len(pkgs)} packages mili (log me dekho).",
                                 TEAL)
            for p in pkgs[:50]:
                self.log("  " + p)
        self._run_bg_cb("list packages", job, done)

    def _pro_backup_apk(self):
        self._pro_set_status("APK backup shuru...", TEAL)
        self._run_bg("backup apk",
                     lambda: features.backup_apks(self.adb, self._serial()))

    def _pro_fb_check(self):
        def job():
            if not self.fb:
                return "ERR: fastboot nahi mila"
            try:
                devs = features.fastboot_devices(self.fb)
            except Exception as exc:
                return "ERR:" + str(exc)
            return f"OK:{len(devs)}" if devs else "NONE:"

        def done(res):
            if res.startswith("OK:"):
                self._pro_set_status(
                    f"✅ Fastboot device mil gaya ({res[3:]})!", TEAL)
            elif res.startswith("ERR:"):
                self._pro_set_status("❌ " + res[4:], DANGER)
            else:
                self._pro_set_status(
                    "❌ Fastboot device nahi mila -- Volume Down + Power se "
                    "fastboot mode me lao.", DANGER)
        self._run_bg_cb("fb check", job, done)

    def _pro_fb_info(self):
        self._pro_set_status("Fastboot info parh rahe hain...", TEAL)
        self._run_bg("fastboot getvar",
                     lambda: features.fastboot_getvar_all(self.fb,
                                                          self._serial()))

    def _pro_frp_erase(self):
        if not self._confirm("FRP ERASE",
                             "Fastboot se FRP partition erase hogi.\n\n"
                             "Bootloader locked hua to phone mana kar dega.\n\n"
                             "Jari rakho?"):
            return
        self._pro_set_status("FRP erase ho raha hai...", TEAL)

        def job():
            try:
                out = features.fastboot_erase(self.fb, "frp", self._serial())
                return "OK:" + str(out)
            except Exception as exc:
                return "ERR:" + str(exc)

        def done(res):
            if res.startswith("OK:"):
                self._pro_set_status("✅ FRP erase ho gaya! Reboot karke check karo.",
                                     TEAL)
            else:
                err = res[4:]
                if "locked" in err.lower() or "not allowed" in err.lower():
                    self._pro_set_status(
                        "⚠️ Bootloader locked -- EDL/BROM wala rasta use karo.",
                        WARN_BG)
                else:
                    self._pro_set_status("❌ " + err, DANGER)
        self._run_bg_cb("frp erase", job, done)

    def _pro_frp_config(self):
        if not self._confirm("Config Erase",
                             "MTK phones par 'config' erase se FRP hat sakta hai.\n\n"
                             "Jari rakho?"):
            return
        self._pro_set_status("Config erase ho raha hai...", TEAL)

        def job():
            try:
                out = features.fastboot_erase(self.fb, "config", self._serial())
                return "OK:" + str(out)
            except Exception as exc:
                return "ERR:" + str(exc)

        def done(res):
            if res.startswith("OK:"):
                self._pro_set_status("✅ Config erase ho gaya!", TEAL)
            else:
                self._pro_set_status("❌ " + res[4:], DANGER)
        self._run_bg_cb("frp config", job, done)

    def _pro_fb_unlock(self):
        if not self._confirm("Unlock Bootloader",
                             "WARNING: Bootloader unlock se phone ka DATA DELETE "
                             "ho jayega!\n\nJari rakho?"):
            return
        self._pro_set_status("Bootloader unlock ho raha hai...", TEAL)
        self._run_bg("fb unlock",
                     lambda: features.fastboot_unlock(self.fb, self._serial()))

    def _pro_fb_lock(self):
        if not self._confirm("Relock Bootloader",
                             "Bootloader dobara lock hoga.\n\nJari rakho?"):
            return
        self._pro_set_status("Bootloader lock ho raha hai...", TEAL)
        self._run_bg("fb lock",
                     lambda: features.fastboot_lock(self.fb, self._serial()))

    def _pro_fb_reboot(self):
        self._pro_set_status("Reboot ho raha hai...", TEAL)
        self._run_bg("fb reboot",
                     lambda: features.fastboot_reboot(self.fb, self._serial()))

    def _pro_edl_guide(self):
        brand = self._pro_state.get("brand")
        if brand and brand in edl.BRAND_EDL:
            info = edl.BRAND_EDL[brand]
            self._pro_set_status(f"📍 {info.get('name', brand)}: "
                                 f"{info.get('method', 'Test Point tab dekho')}",
                                 TEAL)
        else:
            self._pro_set_status(
                "Pehle upar se brand chuno, phir Test Point guide dekho. "
                "EDL/BROM flashing ke liye vendor DA files darkar hoti hain.",
                WARN_BG)
        self.log("EDL/BROM: seedhi baat -- flashing ke liye vendor tools/DA "
                 "files darkar; ye tool guide + fastboot deta hai.")

    def _pro_drivers(self):
        self._pro_set_status("Drivers check ho rahe hain...", TEAL)
        self._run_bg("driver check", drivers.check_drivers)

    def _pro_iphone(self):
        self._pro_set_status("iPhone: libimobiledevice tools check...", TEAL)
        self._run_bg("iphone tools", iphone.check_tools)

    def _pro_backup(self):
        self._pro_set_status("Device report ban raha hai...", TEAL)
        self._run_bg("device report",
                     lambda: features.device_report(self.adb, self._serial()))

    def _pro_guides(self):
        self._pro_set_status("Guides: log me dekho.", TEAL)
        self.log("Guides: FRP/MDM/Flash -- har brand ke notes Brands section me hain.")

    def _pro_users(self):
        if not self.current_is_admin:
            self._pro_set_status("❌ Sirf admin Users dekh sakta hai.", DANGER)
            return
        self._pro_set_status("Users: admin panel (purana Users tab jaisa)...", TEAL)
        self.log("Users: naya user add/block ke liye -- v8 me jald wapis aayega.")

    def _pro_publish(self):
        if not self.current_is_admin:
            self._pro_set_status("❌ Sirf admin publish kar sakta hai.", DANGER)
            return
        self._pro_set_status("Publish: v8 me jald wapis aayega.", TEAL)

    # ================= END v8.0 PRO UI =================

    def _header(self):
        head = tk.Frame(self, bg=ACCENT, height=66)
        head.pack(fill="x")
        head.pack_propagate(False)
        tk.Label(head, text=f"  HAMZA GSM TOOL  v{__version__}", bg=ACCENT, fg="#ffffff",
                 font=("Arial", 20, "bold")).pack(side="left", pady=10)
        tk.Label(head, text="Mobile Servicing Toolkit  •  Pakistan Edition",
                 bg=ACCENT, fg="#e0dcff",
                 font=("Arial", 10)).pack(side="left", padx=12, pady=10)
        strip = tk.Frame(self, bg=TEAL, height=4)
        strip.pack(fill="x")

    def _conn_bar(self):
        bar = tk.Frame(self, bg=BG, pady=6)
        bar.pack(fill="x", padx=10)
        tk.Label(bar, text="Device serial (blank = default):",
                 bg=BG, fg=MUTED, font=("Arial", 10)).pack(side="left")
        tk.Entry(bar, textvariable=self.serial, width=24, bg=PANEL, fg=FG,
                 insertbackground=FG, relief="flat",
                 highlightthickness=1, highlightbackground="#3a3a55",
                 font=("Arial", 10)).pack(side="left", padx=8)
        self._btn(bar, "Refresh devices", self.refresh).pack(side="left")
        self._btn(bar, "\u27f3 Check for Updates",
                  self._check_updates, bg=CARD, fg=FG).pack(side="left", padx=6)
        self._btn(bar, "\u2699", self._update_settings,
                  bg=CARD, fg=FG).pack(side="left")
        self._btn(bar, "Logout", self._logout, bg=CARD, fg=FG).pack(side="right")

    def _tabs(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED,
                        padding=(12, 8), font=("Arial", 10, "bold"), borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])
        style.configure("Treeview", background=PANEL, foreground=FG,
                        fieldbackground=PANEL, rowheight=26, borderwidth=0,
                        font=("Arial", 10))
        style.configure("Treeview.Heading", background=CARD, foreground=FG,
                        font=("Arial", 10, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", ACCENT)])

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=6)

        self.tab_brands = tk.Frame(self.nb, bg=BG)
        self.tab_device = tk.Frame(self.nb, bg=BG)
        self.tab_mdm = tk.Frame(self.nb, bg=BG)
        self.tab_transsion = tk.Frame(self.nb, bg=BG)
        self.tab_meta = tk.Frame(self.nb, bg=BG)
        self.tab_spd = tk.Frame(self.nb, bg=BG)
        self.tab_frp = tk.Frame(self.nb, bg=BG)
        self.tab_flash = tk.Frame(self.nb, bg=BG)
        self.tab_drivers = tk.Frame(self.nb, bg=BG)
        self.tab_edl = tk.Frame(self.nb, bg=BG)
        self.tab_backup = tk.Frame(self.nb, bg=BG)
        self.tab_iphone = tk.Frame(self.nb, bg=BG)
        self.tab_guides = tk.Frame(self.nb, bg=BG)
        self.tab_release = tk.Frame(self.nb, bg=BG)
        self.tab_users = tk.Frame(self.nb, bg=BG)  # admin only, added after login
        self.nb.add(self.tab_brands, text="  Brands  ")
        self.nb.add(self.tab_device, text="  Device  ")
        self.nb.add(self.tab_mdm, text="  MDM  ")
        self.nb.add(self.tab_frp, text="  FRP  ")
        self.nb.add(self.tab_transsion, text="  Transsion  ")
        self.nb.add(self.tab_meta, text="  META  ")
        self.nb.add(self.tab_spd, text="  SPD  ")
        self.nb.add(self.tab_flash, text="  Flash  ")
        self.nb.add(self.tab_drivers, text="  Drivers  ")
        self.nb.add(self.tab_edl, text="  Test Point  ")
        self.nb.add(self.tab_backup, text="  Backup  ")
        self.nb.add(self.tab_iphone, text="  iPhone  ")
        self.nb.add(self.tab_guides, text="  Guides  ")
        self.nb.add(self.tab_release, text="  Publish  ")

        self._build_brands_tab()
        self._build_device_tab()
        self._build_mdm_tab()
        self._build_frp_tab()
        self._build_transsion_tab()
        self._build_meta_tab()
        self._build_spd_tab()
        self._build_flash_tab()
        self._build_drivers_tab()
        self._build_edl_tab()
        self._build_backup_tab()
        self._build_iphone_tab()
        self._build_guides_tab()
        self._build_release_tab()
        self._build_users_tab()

    # ------------------------- brands dashboard -------------------------
    def _build_brands_tab(self):
        # dashboard (tile grid)
        self.dash_frame = tk.Frame(self.tab_brands, bg=BG)
        self.dash_frame.pack(fill="both", expand=True)
        tk.Label(self.dash_frame, text="Brand select karo:",
                 bg=BG, fg=FG, font=("Arial", 12, "bold")).pack(anchor="w",
                                                                padx=18, pady=(10, 2))
        rows = (len(BRAND_TILES) + TILE_COLS - 1) // TILE_COLS
        cw = TILE_PAD + TILE_COLS * (TILE_W + TILE_PAD)
        ch = TILE_PAD + rows * (TILE_H + TILE_PAD)
        wrap = tk.Frame(self.dash_frame, bg=BG)
        wrap.pack(expand=True)
        self.tile_canvas = tk.Canvas(wrap, width=cw, height=ch, bg=BG,
                                     highlightthickness=0)
        self.tile_canvas.pack(pady=6)
        for i, (key, badge, name, color, fg) in enumerate(BRAND_TILES):
            r, c = divmod(i, TILE_COLS)
            x1 = TILE_PAD + c * (TILE_W + TILE_PAD)
            y1 = TILE_PAD + r * (TILE_H + TILE_PAD)
            x2, y2 = x1 + TILE_W, y1 + TILE_H
            tag = f"tile_{key}"
            rounded_rect(self.tile_canvas, x1, y1, x2, y2, 20,
                         fill=color, outline="", tags=tag)
            self.tile_canvas.create_text((x1 + x2) / 2, y1 + 40, text=badge,
                                         font=("Arial", 28, "bold"), fill=fg,
                                         tags=tag)
            self.tile_canvas.create_text((x1 + x2) / 2, y2 - 24, text=name,
                                         font=("Arial", 11, "bold"), fill=fg,
                                         tags=tag)
            self.tile_canvas.tag_bind(tag, "<Button-1>",
                                      lambda _e, k=key: self.show_brand_detail(k))
            self.tile_canvas.tag_bind(tag, "<Enter>",
                                      lambda _e: self.tile_canvas.config(cursor="hand2"))
            self.tile_canvas.tag_bind(tag, "<Leave>",
                                      lambda _e: self.tile_canvas.config(cursor=""))

        # detail view (hidden until a tile is clicked)
        self.detail_frame = tk.Frame(self.tab_brands, bg=BG)

        dhead = tk.Frame(self.detail_frame, bg=BG)
        dhead.pack(fill="x", padx=12, pady=8)
        self._btn(dhead, "← Back", self.show_dashboard,
                  bg=CARD, fg=FG).pack(side="left")
        self.badge_canvas = tk.Canvas(dhead, width=56, height=56, bg=BG,
                                      highlightthickness=0)
        self.badge_canvas.pack(side="left", padx=12)
        self.detail_name = tk.Label(dhead, text="", bg=BG, fg=FG,
                                    font=("Arial", 16, "bold"))
        self.detail_name.pack(side="left")
        self.detail_count = tk.Label(dhead, text="", bg=BG, fg=MUTED,
                                     font=("Arial", 10))
        self.detail_count.pack(side="left", padx=10)

        srow = tk.Frame(self.detail_frame, bg=BG)
        srow.pack(fill="x", padx=12, pady=4)
        tk.Label(srow, text="Search model:", bg=BG, fg=MUTED,
                 font=("Arial", 10, "bold")).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        tk.Entry(srow, textvariable=self.search_var, width=30, bg=PANEL, fg=FG,
                 insertbackground=FG, relief="flat",
                 highlightthickness=1, highlightbackground="#3a3a55",
                 font=("Arial", 10)).pack(side="left", padx=8)

        cols = ("model", "code", "chipset")
        self.model_tree = ttk.Treeview(self.detail_frame, columns=cols,
                                       show="headings", height=9)
        self.model_tree.heading("model", text="Model")
        self.model_tree.heading("code", text="Code")
        self.model_tree.heading("chipset", text="Chipset")
        self.model_tree.column("model", width=280)
        self.model_tree.column("code", width=160)
        self.model_tree.column("chipset", width=280)
        self.model_tree.pack(fill="x", padx=12, pady=4)

        tk.Label(self.detail_frame,
                 text="Model codes device par verify karo -- ghalat firmware = brick!",
                 bg=WARN_BG, fg="#ffd9d9", font=("Arial", 9, "bold"),
                 padx=8, pady=4).pack(fill="x", padx=12, pady=4)

        self.detail_cheat = self._dark_text(self.detail_frame, 8)
        self.detail_cheat.pack(fill="both", expand=True, padx=12, pady=4)

    def show_brand_detail(self, key):
        if key == "apple":
            # iPhone ka apna dedicated tab hai (Android DB me nahi hai)
            self.nb.select(self.tab_iphone)
            return
        info = next(t for t in BRAND_TILES if t[0] == key)
        _, badge, name, color, fg = info
        self._brand_key = key
        self.dash_frame.pack_forget()
        self.detail_frame.pack(fill="both", expand=True)
        self.badge_canvas.delete("all")
        rounded_rect(self.badge_canvas, 2, 2, 54, 54, 14, fill=color, outline="")
        self.badge_canvas.create_text(28, 28, text=badge,
                                      font=("Arial", 18, "bold"), fill=fg)
        self.detail_name.config(text=name)
        self.detail_count.config(text=f"{models.model_count(key)} models")
        self.search_var.set("")
        self._populate_models(models.get_models(key))
        self.detail_cheat.delete("1.0", "end")
        self.detail_cheat.insert("end", brands.cheat_sheet(key))

    def show_dashboard(self):
        self.detail_frame.pack_forget()
        self.dash_frame.pack(fill="both", expand=True)
        self._brand_key = None

    def _on_search(self, *_args):
        if not self._brand_key:
            return
        self._populate_models(
            models.search_models(self._brand_key, self.search_var.get()))

    def _populate_models(self, rows):
        self.model_tree.delete(*self.model_tree.get_children())
        for m in rows:
            self.model_tree.insert("", "end", values=(
                m["model"], m["code"] or "--", m["chipset"]))

    # ---------------------------- device tab ----------------------------
    def _build_device_tab(self):
        self._btn(self.tab_device, "Read device info",
                  self.read_info).pack(anchor="w", padx=12, pady=8)
        self._btn(self.tab_device, "Phone Locked? Madad",
                  self._locked_wizard, bg=WARN_BG).pack(anchor="w", padx=12,
                                                       pady=(0, 8))
        self.info_text = self._dark_text(self.tab_device, 10)
        self.info_text.pack(fill="both", expand=True, padx=12, pady=4)
        row = tk.Frame(self.tab_device, bg=BG)
        row.pack(fill="x", padx=12, pady=8)
        for target in features.REBOOT_TARGETS:
            color = TEAL if target == "meta" else ACCENT
            self._btn(row, f"Reboot: {target}",
                      lambda t=target: self.reboot(t), bg=color).pack(side="left",
                                                                      padx=3)

    def _locked_wizard(self):
        """Phone locked hai? -- honest helper wizard."""
        dlg = tk.Toplevel(self)
        dlg.title("Phone Locked? -- Madad")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        self._center_dialog(dlg, 640, 560)
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="PHONE LOCKED? -- MADAD", bg=BG, fg=WARN_BG,
                 font=("Arial", 14, "bold")).pack(pady=(14, 4))
        top = tk.Frame(dlg, bg=BG)
        top.pack(fill="x", padx=16, pady=6)
        tk.Label(top, text="Brand chuno:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).pack(side="left")
        names = [n for _, _, n, _, _ in BRAND_TILES]
        keys = [k for k, _, _, _, _ in BRAND_TILES]
        brand_var = tk.StringVar(value=names[0])
        combo = ttk.Combobox(top, textvariable=brand_var, values=names,
                             state="readonly", width=24,
                             font=("Arial", 10))
        combo.pack(side="left", padx=8)

        txt = self._dark_text(dlg, 12)
        txt.pack(fill="both", expand=True, padx=16, pady=4)

        def show_brand(_e=None):
            key = keys[names.index(brand_var.get())]
            txt.config(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", lockedhelp.help_text(key))
            txt.config(state="disabled")

        combo.bind("<<ComboboxSelected>>", show_brand)
        show_brand()

        brow = tk.Frame(dlg, bg=BG)
        brow.pack(pady=10)
        self._btn(brow, "Fastboot check karo",
                  lambda: self._locked_fastboot_check(txt),
                  bg=TEAL).pack(side="left", padx=6)
        self._btn(brow, "Band karo", dlg.destroy, bg=CARD, fg=FG).pack(
            side="left", padx=6)

    def _locked_fastboot_check(self, txt):
        """Asal fastboot check -- locked phone fastboot me hai ya nahi."""
        import subprocess
        if not self.fb:
            out = "Fastboot tool nahi mila (platform-tools install karo)."
        else:
            try:
                p = subprocess.run([self.fb, "devices"], capture_output=True,
                                   text=True, timeout=20)
                devs = [l for l in p.stdout.splitlines() if l.strip()]
                if devs:
                    out = ("Fastboot me phone MIL GAYA:\n" + "\n".join(devs) +
                           "\n\nAb Device tab se 'fastboot' wale options "
                           "dekh sakte ho.")
                else:
                    out = ("Fastboot me koi phone NAHI mila.\n"
                           "Phone ko fastboot mode me dalo (upar key combo), "
                           "phir dobara check karo.")
            except Exception as exc:
                out = f"Check nahi ho saka: {exc}"
        txt.config(state="normal")
        txt.insert("end", "\n\n--- FASTBOOT CHECK ---\n" + out)
        txt.config(state="disabled")
        txt.see("end")
        self.log("Locked helper: fastboot check")

    # ------------------------------ mdm tab ------------------------------
    def _build_mdm_tab(self):
        # ---- MDM Easy Fix: sirf 3 steps ----
        easy = tk.LabelFrame(self.tab_mdm, text="  MDM Easy Fix (sirf 3 steps)  ",
                             bg=BG, fg=TEAL, font=("Arial", 11, "bold"),
                             padx=10, pady=8)
        easy.pack(fill="x", padx=12, pady=(10, 4))
        self.mdm_step1 = tk.Label(easy, text="1️⃣ Phone USB se lagao (USB debugging ON)",
                                  bg=BG, fg=FG, font=("Arial", 10))
        self.mdm_step1.pack(anchor="w", pady=2)
        self._btn(easy, "Device check karo",
                  self._mdm_easy_check, bg=CARD, fg=FG).pack(anchor="w", pady=2)
        self.mdm_step2 = tk.Label(easy, text="2️⃣ MDM Scan karo",
                                  bg=BG, fg=FG, font=("Arial", 10))
        self.mdm_step2.pack(anchor="w", pady=(6, 2))
        self._btn(easy, "MDM Scan karo",
                  self._mdm_easy_scan, bg=CARD, fg=FG).pack(anchor="w", pady=2)
        self.mdm_step3 = tk.Label(easy, text="3️⃣ Ek click me MDM Fix karo",
                                  bg=BG, fg=FG, font=("Arial", 10))
        self.mdm_step3.pack(anchor="w", pady=(6, 2))
        self._btn(easy, "MDM FIX KARO",
                  self._mdm_easy_fix, bg=TEAL).pack(anchor="w", pady=2)
        self.mdm_status = tk.Label(easy, text="",
                                   bg=BG, fg=MUTED, font=("Arial", 9),
                                   wraplength=860, justify="left")
        self.mdm_status.pack(anchor="w", pady=(6, 0))
        self._mdm_found = []

        tk.Label(self.tab_mdm,
                 text="Advanced: neeche list me se khud select karke bhi disable/uninstall kar sakte ho.",
                 bg=BG, fg=MUTED, font=("Arial", 9),
                 wraplength=880, justify="left").pack(anchor="w", padx=12, pady=(4, 0))
        btns = tk.Frame(self.tab_mdm, bg=BG)
        btns.pack(fill="x", padx=12, pady=4)
        self._btn(btns, "Scan packages", self.scan_pkgs).pack(side="left", padx=3)
        self._btn(btns, "Show device admins",
                  self.show_admins).pack(side="left", padx=3)
        self.pkg_list = tk.Listbox(self.tab_mdm, selectmode="extended", height=10,
                                   bg=PANEL, fg=FG, selectbackground=ACCENT,
                                   relief="flat", highlightthickness=1,
                                   highlightbackground="#3a3a55",
                                   font=("Arial", 10))
        self.pkg_list.pack(fill="both", expand=True, padx=12, pady=6)
        acts = tk.Frame(self.tab_mdm, bg=BG)
        acts.pack(fill="x", padx=12, pady=8)
        self._btn(acts, "Disable selected (reversible)",
                  lambda: self.pkg_action("disable"),
                  bg=TEAL).pack(side="left", padx=3)
        self._btn(acts, "Uninstall selected (keep data)",
                  lambda: self.pkg_action("uninstall"),
                  bg="#b07cff").pack(side="left", padx=3)

    # ------------------------------- frp tab -------------------------------
    def _build_frp_tab(self):
        tk.Label(self.tab_frp,
                 text="FRP Reset -- Factory Reset Protection hatana.",
                 bg=BG, fg=FG, font=("Arial", 12, "bold")).pack(anchor="w",
                                                               padx=12, pady=(10, 2))
        tk.Label(self.tab_frp,
                 text="Phone ko Fastboot mode me lao (taqreeban: Volume Down + Power). "
                      "Sirf apne phone ya customer ki ijazat se use karo.",
                 bg=BG, fg=MUTED, font=("Arial", 10),
                 wraplength=900, justify="left").pack(anchor="w", padx=12,
                                                      pady=4)
        # ---- 1-click FRP reset ----
        easy = tk.LabelFrame(self.tab_frp, text="  FRP Reset (Fastboot)  ",
                             bg=BG, fg=TEAL, font=("Arial", 10, "bold"),
                             padx=10, pady=8)
        easy.pack(fill="x", padx=12, pady=8)
        self.frp_status = tk.Label(easy, text="", bg=BG, fg=FG,
                                   font=("Arial", 10), wraplength=860,
                                   justify="left")
        self.frp_status.pack(anchor="w", pady=(0, 6))
        brow = tk.Frame(easy, bg=BG)
        brow.pack(fill="x")
        self._btn(brow, "1. Fastboot check karo",
                  self._frp_check, bg=CARD, fg=FG).pack(side="left", padx=3)
        self._btn(brow, "2. FRP ERASE KARO",
                  self._frp_erase, bg=DANGER).pack(side="left", padx=3)
        self._btn(brow, "3. Config Erase (MTK)",
                  self._frp_erase_config, bg=CARD, fg=FG).pack(side="left",
                                                               padx=3)
        # ---- honesty note ----
        note = tk.LabelFrame(self.tab_frp, text="  Zaroori baat  ",
                             bg=BG, fg=WARN_BG, font=("Arial", 10, "bold"),
                             padx=10, pady=8)
        note.pack(fill="x", padx=12, pady=8)
        tk.Label(note,
                 text="Seedhi baat: agar phone ka bootloader LOCKED hai to "
                      "fastboot erase kaam NAHI karega (phone mana kar dega).\n"
                      "Us surat me Test Point / EDL-BROM wala rasta use karo -- "
                      "neeche button se seedha wahan jao.",
                 bg=BG, fg=FG, font=("Arial", 10),
                 wraplength=860, justify="left").pack(anchor="w")
        self._btn(note, "Test Point / EDL tab kholo",
                  lambda: self.nb.select(self.tab_edl),
                  bg=TEAL).pack(anchor="w", pady=(8, 0))

    def _frp_check(self):
        def job():
            if not self.fb:
                return "ERR: fastboot nahi mila"
            try:
                devs = features.fastboot_devices(self.fb)
            except Exception as exc:
                return "ERR:" + str(exc)
            if devs:
                return f"OK:{len(devs)}"
            return "NONE:"

        def done(res):
            if res.startswith("OK:"):
                self.frp_status.config(
                    text=f"✅ Fastboot me phone mil gaya ({res[3:]}) -- "
                         "ab 'FRP ERASE KARO' dabao.", fg=TEAL)
            elif res.startswith("ERR:"):
                self.frp_status.config(text="❌ " + res[4:], fg=DANGER)
            else:
                self.frp_status.config(
                    text="❌ Fastboot me phone nahi mila -- Volume Down + Power "
                         "se fastboot mode me lao, phir dobara check karo.",
                    fg=DANGER)
            self.log("FRP check: " + res)
        self._run_bg_cb("frp check", job, done)

    def _frp_erase(self):
        if not self._confirm("FRP ERASE",
                             "Fastboot se FRP partition erase hogi.\n\n"
                             "Bootloader locked hua to phone mana kar dega -- "
                             "koi nuksan nahi hoga.\n\nJari rakho?"):
            return

        def job():
            try:
                out = features.fastboot_erase(self.fb, "frp",
                                              self._serial())
                return "OK:" + str(out)
            except Exception as exc:
                return "ERR:" + str(exc)

        def done(res):
            if res.startswith("OK:"):
                self.frp_status.config(
                    text="✅ FRP erase ho gaya! Ab phone ko reboot karke "
                         "check karo.", fg=TEAL)
            else:
                err = res[4:]
                if "locked" in err.lower() or "not allowed" in err.lower():
                    self.frp_status.config(
                        text="⚠️ Bootloader locked hai -- fastboot erase mumkin "
                             "nahi. Test Point / EDL wala rasta use karo "
                             "(neeche button).", fg=WARN_BG)
                else:
                    self.frp_status.config(text="❌ " + err, fg=DANGER)
            self.log("FRP erase: " + res)
        self._run_bg_cb("frp erase", job, done)

    def _frp_erase_config(self):
        if not self._confirm("Config Erase",
                             "MTK phones par kabhi 'config' partition erase "
                             "karne se FRP hat jata hai.\n\nJari rakho?"):
            return

        def job():
            try:
                out = features.fastboot_erase(self.fb, "config",
                                              self._serial())
                return "OK:" + str(out)
            except Exception as exc:
                return "ERR:" + str(exc)

        def done(res):
            if res.startswith("OK:"):
                self.frp_status.config(
                    text="✅ Config erase ho gaya! Reboot karke check karo.",
                    fg=TEAL)
            else:
                self.frp_status.config(text="❌ " + res[4:], fg=DANGER)
            self.log("FRP config erase: " + res)
        self._run_bg_cb("frp config erase", job, done)

    # ------------------------- transsion id tab -------------------------
    def _build_transsion_tab(self):
        tk.Label(self.tab_transsion,
                 text="Tecno / Infinix / Itel ID-lock apps scan karo. YOU choose "
                      "what to disable -- nothing is removed automatically.",
                 bg=BG, fg=MUTED, font=("Arial", 10),
                 wraplength=880, justify="left").pack(anchor="w", padx=12, pady=8)
        tk.Label(self.tab_transsion,
                 text="Latest security patch par Transsion ID remove ke liye aam tor par "
                      "BROM-level tools (paid) darkar hote hain. Ye feature ADB access "
                      "milne par kaam karta hai.",
                 bg=WARN_BG, fg="#ffd9d9", font=("Arial", 9, "bold"),
                 wraplength=880, justify="left",
                 padx=8, pady=6).pack(fill="x", padx=12, pady=4)
        btns = tk.Frame(self.tab_transsion, bg=BG)
        btns.pack(fill="x", padx=12, pady=4)
        self._btn(btns, "Scan Transsion ID apps",
                  self.scan_transsion_pkgs).pack(side="left", padx=3)
        self.tid_list = tk.Listbox(self.tab_transsion, selectmode="extended",
                                   height=10, bg=PANEL, fg=FG,
                                   selectbackground=ACCENT, relief="flat",
                                   highlightthickness=1,
                                   highlightbackground="#3a3a55",
                                   font=("Arial", 10))
        self.tid_list.pack(fill="both", expand=True, padx=12, pady=6)
        acts = tk.Frame(self.tab_transsion, bg=BG)
        acts.pack(fill="x", padx=12, pady=8)
        self._btn(acts, "Disable selected (reversible)",
                  lambda: self.transsion_pkg_action("disable"),
                  bg=TEAL).pack(side="left", padx=3)
        self._btn(acts, "Uninstall selected (keep data)",
                  lambda: self.transsion_pkg_action("uninstall"),
                  bg="#b07cff").pack(side="left", padx=3)

    def scan_transsion_pkgs(self):
        def job():
            pkgs = features.list_packages(self.adb, self._serial())
            found = features.find_transsion_id_packages(pkgs)
            self.tid_list.delete(0, "end")
            for p in found:
                self.tid_list.insert("end", p)
            return (f"scanned {len(pkgs)} packages, "
                    f"Transsion ID-like: {found or 'none'}")
        self._run_bg("scan transsion id", job)

    def transsion_pkg_action(self, what):
        sel = [self.tid_list.get(i) for i in self.tid_list.curselection()]
        if not sel:
            messagebox.showinfo("Transsion ID",
                                "Pehle list me se package select karo.")
            return
        if not self._confirm("Confirm",
                             f"{what.upper()} these packages?\n" + "\n".join(sel)):
            return

        def job():
            res = []
            for pkg in sel:
                if what == "disable":
                    features.disable_package(self.adb, pkg, self._serial())
                else:
                    features.uninstall_package(self.adb, pkg, self._serial())
                res.append(f"{what}d: {pkg}")
            return "\n".join(res)
        self._run_bg(f"{what} transsion packages", job)

    # ---------------------------- meta mode tab ----------------------------
    def _build_meta_tab(self):
        tk.Label(self.tab_meta,
                 text="MTK phones ke liye IMEI / NVRAM work area.",
                 bg=BG, fg=FG, font=("Arial", 12, "bold")).pack(anchor="w",
                                                               padx=12, pady=(10, 2))
        tk.Label(self.tab_meta,
                 text="Ye toolkit phone ko META mode me bhejta hai; actual IMEI write "
                      "vendor tool (Modem META / Maui META) se hota hai -- wo alag se chahiye.",
                 bg=BG, fg=MUTED, font=("Arial", 10),
                 wraplength=880, justify="left").pack(anchor="w", padx=12, pady=4)
        self._btn(self.tab_meta, "REBOOT TO META MODE",
                  lambda: self.reboot("meta"),
                  bg=TEAL).pack(anchor="w", padx=12, pady=8)
        # ---- MDM helper: META mode me MDM fix NAHI ho sakta (honest) ----
        mdm_box = tk.LabelFrame(self.tab_meta, text="  MDM lock ka masla hai?  ",
                                bg=BG, fg=TEAL, font=("Arial", 10, "bold"),
                                padx=10, pady=8)
        mdm_box.pack(fill="x", padx=12, pady=8)
        tk.Label(mdm_box,
                 text="Seedhi baat: META mode me phone ka Android band hota hai, "
                      "is liye MDM apps yahan se disable NAHI ho sakti.\n"
                      "MDM fix ke liye phone normal mode me hona chahiye (USB debugging ON).",
                 bg=BG, fg=FG, font=("Arial", 10),
                 wraplength=860, justify="left").pack(anchor="w")
        brow2 = tk.Frame(mdm_box, bg=BG)
        brow2.pack(fill="x", pady=(8, 0))
        self._btn(brow2, "1. Reboot to System",
                  lambda: self.reboot("system"),
                  bg=CARD, fg=FG).pack(side="left", padx=3)
        self._btn(brow2, "2. MDM tab kholo (Easy Fix)",
                  self._goto_mdm_tab, bg=TEAL).pack(side="left", padx=3)
        tk.Label(self.tab_meta,
                 text="Sirf ORIGINAL IMEI restore karo -- Pakistan me IMEI tamper illegal hai (PTA).",
                 bg=WARN_BG, fg="#ffd9d9", font=("Arial", 10, "bold"),
                 wraplength=880, justify="left",
                 padx=8, pady=6).pack(fill="x", padx=12, pady=6)
        tk.Label(self.tab_meta, text="Workflow:",
                 bg=BG, fg=FG, font=("Arial", 10, "bold")).pack(anchor="w",
                                                                padx=12, pady=(6, 2))
        wf = self._dark_text(self.tab_meta, 12)
        wf.pack(fill="both", expand=True, padx=12, pady=4)
        wf.insert("end", brands.IMEI_WORKFLOW + "\n")

    def _goto_mdm_tab(self):
        self.nb.select(self.tab_mdm)
        self.log("MDM tab khola (META helper se)")

    # ------------------------------- spd tab -------------------------------
    def _build_spd_tab(self):
        tk.Label(self.tab_spd,
                 text="SPD / Unisoc phones -- ADB wale sare features yahan bhi kaam karte hain.",
                 bg=BG, fg=FG, font=("Arial", 12, "bold")).pack(anchor="w",
                                                                padx=12, pady=(10, 2))
        btns = tk.Frame(self.tab_spd, bg=BG)
        btns.pack(fill="x", padx=12, pady=6)
        self._btn(btns, "Read device info",
                  self.read_info).pack(side="left", padx=3)
        for target in ("system", "recovery", "bootloader"):
            self._btn(btns, f"Reboot: {target}",
                      lambda t=target: self.reboot(t)).pack(side="left", padx=3)
        tk.Label(self.tab_spd,
                 text="PAC flashing is toolkit ka hissa nahi -- SPD Upgrade Tool alag se chahiye.",
                 bg=WARN_BG, fg="#ffd9d9", font=("Arial", 9, "bold"),
                 wraplength=880, justify="left",
                 padx=8, pady=6).pack(fill="x", padx=12, pady=6)
        tk.Label(self.tab_spd, text="SPD notes:",
                 bg=BG, fg=FG, font=("Arial", 10, "bold")).pack(anchor="w",
                                                                padx=12, pady=(4, 2))
        notes = self._dark_text(self.tab_spd, 10)
        notes.pack(fill="both", expand=True, padx=12, pady=4)
        notes.insert("end", brands.SPD_NOTES + "\n")

    # ---------------------------- flashing tab ----------------------------
    def _build_flash_tab(self):
        tk.Label(self.tab_flash,
                 text="DANGER: flashing the wrong image can permanently brick "
                      "the phone. Use only firmware for the EXACT model.",
                 bg=WARN_BG, fg="#ffd9d9", font=("Arial", 10, "bold"),
                 wraplength=880, justify="left",
                 padx=8, pady=6).pack(fill="x", padx=12, pady=8)
        fbtns = tk.Frame(self.tab_flash, bg=BG)
        fbtns.pack(fill="x", padx=12, pady=4)
        self._btn(fbtns, "Bootloader UNLOCK", self.fb_unlock,
                  bg=DANGER).pack(side="left", padx=3)
        self._btn(fbtns, "Bootloader LOCK", self.fb_lock,
                  bg=CARD, fg=FG).pack(side="left", padx=3)
        self._btn(fbtns, "fastboot devices", self.fb_devices).pack(side="left",
                                                                   padx=3)
        frm = tk.Frame(self.tab_flash, bg=BG)
        frm.pack(fill="x", padx=12, pady=10)
        tk.Label(frm, text="Partition:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).pack(side="left")
        self.part_var = tk.StringVar(value="boot")
        tk.Entry(frm, textvariable=self.part_var, width=14, bg=PANEL, fg=FG,
                 insertbackground=FG, relief="flat",
                 highlightthickness=1, highlightbackground="#3a3a55",
                 font=("Arial", 10)).pack(side="left", padx=8)
        self._btn(frm, "Choose image…", self.choose_image,
                  bg=CARD, fg=FG).pack(side="left")
        self.img_var = tk.StringVar()
        tk.Label(frm, textvariable=self.img_var, bg=BG, fg=MUTED,
                 wraplength=320, font=("Arial", 9)).pack(side="left", padx=8)
        self._btn(self.tab_flash, "FLASH partition", self.fb_flash,
                  bg=DANGER).pack(anchor="w", padx=12, pady=8)

    # ---------------------------- guides tab ----------------------------
    def _build_guides_tab(self):
        brow = tk.Frame(self.tab_guides, bg=BG)
        brow.pack(fill="x", padx=12, pady=8)
        self._btn(brow, "IMEI workflow",
                  lambda: self.show_guide(brands.IMEI_WORKFLOW)).pack(side="left",
                                                                      padx=3)
        self._btn(brow, "FRP guide",
                  lambda: self.show_guide(brands.FRP_WORKFLOW)).pack(side="left",
                                                                     padx=3)
        self._btn(brow, "SPD notes",
                  lambda: self.show_guide(brands.SPD_NOTES)).pack(side="left",
                                                                  padx=3)
        self.guide_text = self._dark_text(self.tab_guides, 20)
        self.guide_text.pack(fill="both", expand=True, padx=12, pady=4)
        self.guide_text.insert("end", "Upar button dabao -- guide yahan aayegi.\n")

    def show_guide(self, text):
        self.guide_text.delete("1.0", "end")
        self.guide_text.insert("end", text + "\n")

    # --------------------------- login system ---------------------------
    def _center_dialog(self, dlg, w, h):
        dlg.update_idletasks()
        x = (dlg.winfo_screenwidth() - w) // 2
        y = (dlg.winfo_screenheight() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")

    def _login_flow(self):
        """Pehli run: admin khud banega, koi dialog nahi -- seedha app khulegi.

        (Purana dialog wala rasta kuch Windows par band ho jata tha,
        is liye pehli run ab bilkul seedhi hai.)
        """
        _stage("stage 6: login flow started")
        if os.environ.get("GSMTOOL_SKIP_LOGIN") == "1":
            # Screenshot/preview only. Never enabled in shipped use.
            users.init_db(USERS_DB)
            self.current_user, self.current_is_admin = "preview", True
            self.deiconify()
            self._after_login()
            return
        users.init_db(USERS_DB)
        _stage("stage 6b: db ready")
        if users.user_count() == 0:
            # PEHLI RUN -- koi dialog nahi, admin auto-banao, seedha andar.
            _stage("stage 6c: auto-creating first admin")
            try:
                users.create_user("admin", "hamza123", is_admin=True)
            except ValueError:
                pass  # pehle se mojood hai
            key = recovery.generate_key()
            try:
                users.set_meta("recovery_key", key)
            except Exception:
                pass
            self.current_user, self.current_is_admin = "admin", True
            self.deiconify()
            self._after_login()
            _stage("stage 6d: first-run admin logged in")
            self._show_first_run_welcome(key)
            return
        # Normal login (users pehle se hain)
        creds = self._login_dialog()
        if creds is None:
            self.destroy()
            return
        self.current_user, self.current_is_admin = creds
        self.deiconify()
        self._after_login()

    def _show_first_run_welcome(self, key):
        """Pehli run par credentials + recovery key dikhao (app khulne ke BAAD)."""
        self.log("First run: admin account ban gaya (admin / hamza123).")
        self.log(f"Recovery key: {key}")
        try:
            messagebox.showinfo(
                "Welcome!",
                "Admin account ban gaya!\n\n"
                "Username: admin\n"
                "Password: hamza123\n\n"
                f"Recovery key (screenshot le lo):\n{key}\n\n"
                "Password baad me Users tab se badal lena.",
                parent=self)
        except Exception:
            pass

    def _after_login(self):
        role = "Admin" if self.current_is_admin else "User"
        self.current_expiry = users.get_expiry(self.current_user)
        self._update_status()
        self.log(f"Login: {self.current_user} ({role})")
        # v8.0: Users management TOOLS mode me hai (Pro UI), tab system khatam.
        if self.current_is_admin and not self._users_tab_added:
            self._users_tab_added = True
            try:
                self._refresh_users()
            except Exception:
                pass
            try:
                self._backup_load_fields()
            except Exception:
                pass
            try:
                self._backup_auto_check()
            except Exception:
                pass

    def _logout(self):
        if not self.current_user:
            return
        # v8.0: no notebook anymore
        self._users_tab_added = False
        self.log(f"Logout: {self.current_user}")
        self.current_user = None
        self.current_is_admin = False
        self.current_expiry = None
        self._update_status()
        self.withdraw()
        self._login_flow()

    def _login_dialog(self):
        """Modal username/password dialog. Returns (username, is_admin) or None."""
        dlg = tk.Toplevel(self)
        dlg.title("Login -- Hamza GSM Tool")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        self._center_dialog(dlg, 380, 250)
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="HAMZA GSM TOOL", bg=BG, fg=ACCENT,
                 font=("Arial", 16, "bold")).pack(pady=(18, 4))
        tk.Label(dlg, text="Login karo", bg=BG, fg=MUTED,
                 font=("Arial", 10)).pack(pady=(0, 10))

        frm = tk.Frame(dlg, bg=BG)
        frm.pack(padx=30, fill="x")
        tk.Label(frm, text="Username:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w",
                                                  pady=4)
        user_e = tk.Entry(frm, bg=PANEL, fg=FG, insertbackground=FG, width=26,
                          relief="flat", highlightthickness=1,
                          highlightbackground="#3a3a55", font=("Arial", 11))
        user_e.grid(row=0, column=1, pady=4, padx=6)
        tk.Label(frm, text="Password:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w",
                                                  pady=4)
        pw_e = tk.Entry(frm, bg=PANEL, fg=FG, insertbackground=FG, width=26,
                        show="*", relief="flat", highlightthickness=1,
                        highlightbackground="#3a3a55", font=("Arial", 11))
        pw_e.grid(row=1, column=1, pady=4, padx=6)

        result = {}

        def do_login():
            u = user_e.get().strip()
            status, is_admin = users.verify(u, pw_e.get())
            if status == "ok":
                result["creds"] = (u, is_admin)
                dlg.destroy()
            elif status == "blocked":
                messagebox.showwarning("Blocked",
                                       "Ye account block hai. Admin se rabta karo.",
                                       parent=dlg)
            elif status == "expired":
                messagebox.showwarning("Expired",
                                       "Is account ki muddat khatam ho gayi hai.\n"
                                       "Renew ke liye admin se rabta karo.",
                                       parent=dlg)
            else:
                # never reveal whether the username exists
                messagebox.showerror("Login failed",
                                     "Ghalat username ya password.",
                                     parent=dlg)

        brow = tk.Frame(dlg, bg=BG)
        brow.pack(pady=16)
        self._btn(brow, "Login", do_login).pack(side="left", padx=6)
        self._btn(brow, "Master Admin",
                  lambda: self._do_master_from_login(dlg, result),
                  bg=TEAL).pack(side="left", padx=6)
        self._btn(brow, "Cancel", dlg.destroy, bg=CARD, fg=FG).pack(side="left",
                                                                    padx=6)
        pw_e.bind("<Return>", lambda _e: do_login())
        user_e.bind("<Return>", lambda _e: do_login())
        user_e.focus_set()
        self.wait_window(dlg)
        return result.get("creds")

    def _do_master_from_login(self, login_dlg, result):
        """Login dialog ke 'Master Admin' button ka handler."""
        creds = self._master_login_dialog(login_dlg)
        if creds:
            result["creds"] = creds
            login_dlg.destroy()

    def _master_login_dialog(self, parent):
        """Recovery key dialog. Returns ('master', True) ya None."""
        dlg = tk.Toplevel(parent)
        dlg.title("Master Admin -- Recovery Key")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        self._center_dialog(dlg, 420, 300)
        dlg.transient(parent)
        dlg.grab_set()

        tk.Label(dlg, text="MASTER ADMIN", bg=BG, fg=TEAL,
                 font=("Arial", 15, "bold")).pack(pady=(18, 4))
        tk.Label(dlg, text="Apni master recovery key dalo.\n"
                           "Naya PC ho ya purana -- key se master admin mil jayega.",
                 bg=BG, fg=MUTED, font=("Arial", 10),
                 justify="center").pack(pady=(0, 10))
        key_e = tk.Entry(dlg, bg=PANEL, fg=FG, insertbackground=FG, width=34,
                         relief="flat", highlightthickness=1,
                         highlightbackground="#3a3a55",
                         font=("Courier", 11))
        key_e.pack(pady=6)

        result = {}

        def do_master():
            if recovery.verify_key(key_e.get()):
                result["creds"] = ("master", True)
                dlg.destroy()
            else:
                messagebox.showerror("Ghalat key",
                                     "Ye recovery key sahi nahi hai.\n"
                                     "Dobara check karke dalo.",
                                     parent=dlg)

        brow = tk.Frame(dlg, bg=BG)
        brow.pack(pady=14)
        self._btn(brow, "Master login", do_master, bg=TEAL).pack(side="left",
                                                                 padx=6)
        self._btn(brow, "Cancel", dlg.destroy, bg=CARD, fg=FG).pack(
            side="left", padx=6)
        key_e.bind("<Return>", lambda _e: do_master())
        key_e.focus_set()
        self.wait_window(dlg)
        return result.get("creds")

    def _admin_setup_dialog(self):
        """First-run dialog: create the admin account. Returns creds or None."""
        dlg = tk.Toplevel(self)
        dlg.title("Admin Account banao")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        self._center_dialog(dlg, 400, 320)
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="Pehla Admin Account banao", bg=BG, fg=ACCENT,
                 font=("Arial", 15, "bold")).pack(pady=(18, 4))
        tk.Label(dlg, text="Ye admin sab users ko manage karega\n(add / block / password reset / delete).",
                 bg=BG, fg=MUTED, font=("Arial", 10), justify="center").pack(pady=(0, 10))

        frm = tk.Frame(dlg, bg=BG)
        frm.pack(padx=30, fill="x")
        tk.Label(frm, text="Username:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=4)
        user_e = tk.Entry(frm, bg=PANEL, fg=FG, insertbackground=FG, width=26,
                          relief="flat", highlightthickness=1,
                          highlightbackground="#3a3a55", font=("Arial", 11))
        user_e.grid(row=0, column=1, pady=4, padx=6)
        tk.Label(frm, text="Password:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", pady=4)
        pw_e = tk.Entry(frm, bg=PANEL, fg=FG, insertbackground=FG, width=26,
                        show="*", relief="flat", highlightthickness=1,
                        highlightbackground="#3a3a55", font=("Arial", 11))
        pw_e.grid(row=1, column=1, pady=4, padx=6)
        tk.Label(frm, text="Confirm:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).grid(row=2, column=0, sticky="w", pady=4)
        pw2_e = tk.Entry(frm, bg=PANEL, fg=FG, insertbackground=FG, width=26,
                         show="*", relief="flat", highlightthickness=1,
                         highlightbackground="#3a3a55", font=("Arial", 11))
        pw2_e.grid(row=2, column=1, pady=4, padx=6)

        result = {}

        def do_create():
            u = user_e.get().strip()
            p1, p2 = pw_e.get(), pw2_e.get()
            if p1 != p2:
                messagebox.showerror("Error", "Password match nahi ho raha.",
                                     parent=dlg)
                return
            try:
                users.create_user(u, p1, is_admin=True)
            except ValueError as exc:
                messagebox.showerror("Error", str(exc), parent=dlg)
                return
            key = recovery.generate_key()
            users.set_meta("recovery_key", key)
            messagebox.showinfo("Ho gaya",
                                f"Admin account '{u}' ban gaya!",
                                parent=dlg)
            result["creds"] = (u, True)
            dlg.destroy()
            self._show_recovery_key_once(key)

        def do_restore():
            if self._backup_restore_flow(dlg):
                result["restored"] = True
                dlg.destroy()

        brow = tk.Frame(dlg, bg=BG)
        brow.pack(pady=16)
        self._btn(brow, "Admin banao", do_create).pack(side="left", padx=6)
        self._btn(brow, "Gmail backup se wapis lao", do_restore,
                  bg=TEAL).pack(side="left", padx=6)
        self._btn(brow, "Cancel", dlg.destroy, bg=CARD, fg=FG).pack(side="left",
                                                                    padx=6)
        user_e.focus_set()
        self.wait_window(dlg)
        return result.get("creds")

    def _show_recovery_key_once(self, key, first_time=True):
        """Recovery key dikhao -- screenshot/likh lo."""
        dlg = tk.Toplevel(self)
        dlg.title("MASTER RECOVERY KEY -- sambhal kar rakho!")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        self._center_dialog(dlg, 480, 340)
        dlg.transient(self)
        dlg.grab_set()
        tk.Label(dlg, text="MASTER RECOVERY KEY", bg=BG, fg=DANGER,
                 font=("Arial", 15, "bold")).pack(pady=(18, 4))
        warn = ("Ye key KISI KO NA DO. PC kharab ho ya naya PC lo --\n"
                "login screen par 'Master Admin' dabakar ye key dalo ge.\n")
        if first_time:
            warn += ("Screenshot le lo ya kaaghaz par likh lo --\n"
                     "ye dobara NAHI dikhegi!")
        else:
            warn += "Screenshot le lo ya kaaghaz par likh lo."
        tk.Label(dlg, text=warn,
                 bg=BG, fg=FG, font=("Arial", 10),
                 justify="center").pack(pady=(0, 8))
        key_lbl = tk.Label(dlg, text=key, bg=PANEL, fg=TEAL,
                           font=("Courier", 12, "bold"), padx=10, pady=10)
        key_lbl.pack(pady=6)

        def do_copy():
            self.clipboard_clear()
            self.clipboard_append(key)
            messagebox.showinfo("Copy", "Key copy ho gayi -- mehfooz jagah "
                                       "paste karke rakho.", parent=dlg)

        brow = tk.Frame(dlg, bg=BG)
        brow.pack(pady=12)
        self._btn(brow, "Copy karo", do_copy, bg=TEAL).pack(side="left",
                                                             padx=6)
        self._btn(brow, "Sambhal li hai", dlg.destroy).pack(side="left",
                                                             padx=6)
        self.wait_window(dlg)

    # ---------------------------- users tab (admin) ----------------------------
    def _build_users_tab(self):
        tk.Label(self.tab_users,
                 text="Users manage karo -- naya user, block/unblock, password reset, delete.",
                 bg=BG, fg=MUTED, font=("Arial", 10),
                 wraplength=880, justify="left").pack(anchor="w", padx=12, pady=8)
        cols = ("username", "role", "status", "expiry")
        self.users_tree = ttk.Treeview(self.tab_users, columns=cols,
                                       show="headings", height=10)
        self.users_tree.heading("username", text="Username")
        self.users_tree.heading("role", text="Role")
        self.users_tree.heading("status", text="Status")
        self.users_tree.heading("expiry", text="Expiry")
        self.users_tree.column("username", width=220)
        self.users_tree.column("role", width=110)
        self.users_tree.column("status", width=110)
        self.users_tree.column("expiry", width=150)
        self.users_tree.pack(fill="both", expand=True, padx=12, pady=4)

        brow = tk.Frame(self.tab_users, bg=BG)
        brow.pack(fill="x", padx=12, pady=10)
        self._btn(brow, "Naya user add karo",
                  self._user_add_dialog).pack(side="left", padx=3)
        self._btn(brow, "Expiry set karo",
                  self._user_set_expiry, bg=TEAL).pack(side="left", padx=3)
        self._btn(brow, "Block / Unblock",
                  self._user_toggle_block, bg=WARN_BG).pack(side="left", padx=3)
        self._btn(brow, "Password reset",
                  self._user_reset_pw, bg=CARD, fg=FG).pack(side="left", padx=3)
        self._btn(brow, "User delete karo",
                  self._user_delete, bg=DANGER).pack(side="left", padx=3)
        self._btn(brow, "Recovery key",
                  self._recovery_key_show, bg=TEAL).pack(side="left", padx=3)
        self._btn(brow, "Refresh",
                  self._refresh_users, bg=CARD, fg=FG).pack(side="left", padx=3)

        # ---- admin auto backup (Gmail) -- sirf admin ko nazar aata hai ----
        bframe = tk.LabelFrame(self.tab_users, text="  ☁ Auto Backup (Gmail)  ",
                               bg=BG, fg=TEAL, font=("Arial", 10, "bold"),
                               padx=10, pady=8)
        bframe.pack(fill="x", padx=12, pady=(0, 12))
        tk.Label(bframe, text="Gmail:",
                 bg=BG, fg=FG, font=("Arial", 10)).grid(row=0, column=0,
                                                        sticky="w", padx=4)
        self.bk_gmail = tk.Entry(bframe, bg=PANEL, fg=FG,
                                 insertbackground=FG, width=30,
                                 font=("Arial", 10))
        self.bk_gmail.grid(row=0, column=1, padx=4)
        tk.Label(bframe, text="App Password:",
                 bg=BG, fg=FG, font=("Arial", 10)).grid(row=0, column=2,
                                                        sticky="w", padx=4)
        self.bk_apppw = tk.Entry(bframe, bg=PANEL, fg=FG,
                                 insertbackground=FG, width=22, show="*",
                                 font=("Arial", 10))
        self.bk_apppw.grid(row=0, column=3, padx=4)
        self.bk_auto_var = tk.BooleanVar(value=False)
        tk.Checkbutton(bframe, text="Har din khud backup bhejo",
                       variable=self.bk_auto_var, bg=BG, fg=FG,
                       selectcolor=PANEL, activebackground=BG,
                       font=("Arial", 10)).grid(row=0, column=4, padx=8)
        self._btn(bframe, "Save karo",
                  self._backup_save, bg=TEAL).grid(row=0, column=5, padx=3)
        self._btn(bframe, "Abhi backup bhejo",
                  self._backup_send_now, bg=CARD, fg=FG).grid(row=0, column=6,
                                                              padx=3)
        self._btn(bframe, "Gmail se wapis lao",
                  self._backup_restore_button, bg=WARN_BG).grid(row=0, column=7,
                                                                padx=3)
        self._btn(bframe, "?",
                  self._backup_help, bg=CARD, fg=FG).grid(row=0, column=8,
                                                         padx=3)
        self.bk_status = tk.Label(bframe, text="Backup set nahi hai.",
                                  bg=BG, fg=MUTED, font=("Arial", 9))
        self.bk_status.grid(row=1, column=0, columnspan=9, sticky="w",
                            padx=4, pady=(6, 0))

    def _refresh_users(self):
        self.users_tree.delete(*self.users_tree.get_children())
        for uname, is_admin, is_blocked, expires_at in users.list_users():
            role = "Admin" if is_admin else "User"
            status = "Blocked" if is_blocked else "Active"
            self.users_tree.insert("", "end",
                                   values=(uname, role, status,
                                           users.fmt_expiry(expires_at)))

    def _user_set_expiry(self):
        uname = self._selected_username()
        if uname is None:
            return
        dlg = tk.Toplevel(self)
        dlg.title("Expiry set karo")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        self._center_dialog(dlg, 360, 220)
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text=f"Expiry: {uname}", bg=BG, fg=ACCENT,
                 font=("Arial", 14, "bold")).pack(pady=(16, 4))
        cur = users.get_expiry(uname)
        tk.Label(dlg, text=f"Maujooda: {users.fmt_expiry(cur)}", bg=BG,
                 fg=MUTED, font=("Arial", 10)).pack(pady=(0, 8))
        dur_var = tk.StringVar()
        cb = ttk.Combobox(dlg, textvariable=dur_var,
                          values=[d[0] for d in users.DURATIONS],
                          state="readonly", width=22, font=("Arial", 11))
        cb.pack(pady=4)
        cb.current(0)

        def do_set():
            secs = dict(users.DURATIONS)[dur_var.get()]
            try:
                users.set_expiry(uname, users.expiry_from_duration(secs))
            except ValueError as exc:
                messagebox.showerror("Error", str(exc), parent=dlg)
                return
            self._refresh_users()
            self.log(f"Expiry set: {uname} -> {users.fmt_expiry(users.get_expiry(uname))}")
            dlg.destroy()

        brow = tk.Frame(dlg, bg=BG)
        brow.pack(pady=14)
        self._btn(brow, "Set karo", do_set).pack(side="left", padx=6)
        self._btn(brow, "Cancel", dlg.destroy, bg=CARD, fg=FG).pack(side="left",
                                                                    padx=6)
        self.wait_window(dlg)

    def _selected_username(self):
        sel = self.users_tree.selection()
        if not sel:
            messagebox.showinfo("Users", "Pehle list me se user select karo.")
            return None
        return self.users_tree.item(sel[0])["values"][0]

    def _user_add_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Naya user")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        self._center_dialog(dlg, 400, 310)
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="Naya user add karo", bg=BG, fg=ACCENT,
                 font=("Arial", 14, "bold")).pack(pady=(16, 8))
        frm = tk.Frame(dlg, bg=BG)
        frm.pack(padx=30, fill="x")
        tk.Label(frm, text="Username:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=4)
        user_e = tk.Entry(frm, bg=PANEL, fg=FG, insertbackground=FG, width=24,
                          relief="flat", highlightthickness=1,
                          highlightbackground="#3a3a55", font=("Arial", 11))
        user_e.grid(row=0, column=1, pady=4, padx=6)
        tk.Label(frm, text="Password:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", pady=4)
        pw_e = tk.Entry(frm, bg=PANEL, fg=FG, insertbackground=FG, width=24,
                        show="*", relief="flat", highlightthickness=1,
                        highlightbackground="#3a3a55", font=("Arial", 11))
        pw_e.grid(row=1, column=1, pady=4, padx=6)
        is_admin_var = tk.BooleanVar(value=False)
        tk.Checkbutton(frm, text="Admin banao", variable=is_admin_var,
                       bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG,
                       font=("Arial", 10)).grid(row=2, column=1, sticky="w", pady=4)
        tk.Label(frm, text="Muddat:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).grid(row=3, column=0, sticky="w", pady=4)
        dur_var = tk.StringVar()
        dur_cb = ttk.Combobox(frm, textvariable=dur_var,
                              values=[d[0] for d in users.DURATIONS],
                              state="readonly", width=22, font=("Arial", 10))
        dur_cb.grid(row=3, column=1, pady=4, padx=6, sticky="w")
        dur_cb.current(0)

        def do_add():
            secs = dict(users.DURATIONS)[dur_var.get()]
            try:
                users.create_user(user_e.get().strip(), pw_e.get(),
                                  is_admin=is_admin_var.get(),
                                  expires_at=users.expiry_from_duration(secs))
            except ValueError as exc:
                messagebox.showerror("Error", str(exc), parent=dlg)
                return
            self._refresh_users()
            self.log(f"User added: {user_e.get().strip()}")
            dlg.destroy()

        brow = tk.Frame(dlg, bg=BG)
        brow.pack(pady=14)
        self._btn(brow, "Add karo", do_add).pack(side="left", padx=6)
        self._btn(brow, "Cancel", dlg.destroy, bg=CARD, fg=FG).pack(side="left",
                                                                    padx=6)
        user_e.focus_set()
        self.wait_window(dlg)

    def _user_toggle_block(self):
        uname = self._selected_username()
        if uname is None:
            return
        if uname == self.current_user:
            messagebox.showwarning("Users", "Khud ko block nahi kar sakte.",
                                   parent=self)
            return
        cur = {u: b for u, _a, b, _e in users.list_users()}.get(uname, False)
        action = "unblock" if cur else "block"
        if not messagebox.askyesno("Confirm",
                                    f"'{uname}' ko {action} karna hai?",
                                    parent=self):
            return
        try:
            users.set_blocked(uname, not cur)
        except ValueError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return
        self._refresh_users()
        self.log(f"User {action}: {uname}")

    def _user_reset_pw(self):
        uname = self._selected_username()
        if uname is None:
            return
        dlg = tk.Toplevel(self)
        dlg.title("Password reset")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        self._center_dialog(dlg, 360, 200)
        dlg.transient(self)
        dlg.grab_set()
        tk.Label(dlg, text=f"'{uname}' ka naya password:",
                 bg=BG, fg=FG, font=("Arial", 11, "bold")).pack(pady=(18, 8))
        pw_e = tk.Entry(dlg, bg=PANEL, fg=FG, insertbackground=FG, width=26,
                        show="*", relief="flat", highlightthickness=1,
                        highlightbackground="#3a3a55", font=("Arial", 11))
        pw_e.pack(pady=4)

        def do_reset():
            try:
                users.reset_password(uname, pw_e.get())
            except ValueError as exc:
                messagebox.showerror("Error", str(exc), parent=dlg)
                return
            messagebox.showinfo("Ho gaya", "Password reset ho gaya.", parent=dlg)
            self.log(f"Password reset: {uname}")
            dlg.destroy()

        brow = tk.Frame(dlg, bg=BG)
        brow.pack(pady=14)
        self._btn(brow, "Reset karo", do_reset).pack(side="left", padx=6)
        self._btn(brow, "Cancel", dlg.destroy, bg=CARD, fg=FG).pack(side="left",
                                                                    padx=6)
        pw_e.focus_set()
        self.wait_window(dlg)

    def _user_delete(self):
        uname = self._selected_username()
        if uname is None:
            return
        if uname == self.current_user:
            messagebox.showwarning("Users", "Khud ko delete nahi kar sakte.",
                                   parent=self)
            return
        if not messagebox.askyesno("Confirm",
                                    f"'{uname}' ko DELETE karna hai? Ye wapas nahi hoga.",
                                    parent=self):
            return
        try:
            users.delete_user(uname)
        except ValueError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return
        self._refresh_users()
        self.log(f"User deleted: {uname}")

    # ------------------- admin auto backup (Gmail) -------------------
    def _backup_base_dir(self):
        return paths.base_dir()

    def _backup_load_fields(self):
        cfg = backup_admin.load_config(self._backup_base_dir())
        self.bk_gmail.delete(0, "end")
        self.bk_gmail.insert(0, cfg.get("gmail", ""))
        self.bk_apppw.delete(0, "end")
        self.bk_apppw.insert(0, cfg.get("app_password", ""))
        self.bk_auto_var.set(bool(cfg.get("auto")))
        self._backup_show_status(cfg)

    def _backup_show_status(self, cfg=None):
        if cfg is None:
            cfg = backup_admin.load_config(self._backup_base_dir())
        if cfg.get("gmail"):
            last = cfg.get("last_backup", 0)
            when = (datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M")
                    if last else "kabhi nahi")
            auto = "ON (har din)" if cfg.get("auto") else "OFF"
            self.bk_status.config(
                text=f"Gmail: {cfg['gmail']} | Auto: {auto} | "
                     f"Aakhri backup: {when}", fg=TEAL)
        else:
            self.bk_status.config(text="Backup set nahi hai.", fg=MUTED)

    def _backup_save(self):
        cfg = backup_admin.save_config(
            self._backup_base_dir(),
            self.bk_gmail.get(), self.bk_apppw.get(),
            self.bk_auto_var.get())
        self._backup_show_status(cfg)
        self.log("Backup settings save ho gayi.")
        messagebox.showinfo("Backup", "Gmail settings save ho gayi.",
                            parent=self)

    def _backup_send_now(self):
        self._backup_save_silent()
        self.bk_status.config(text="Backup bheja ja raha hai...", fg=FG)
        threading.Thread(target=self._backup_send_thread,
                         daemon=True).start()

    def _backup_save_silent(self):
        cfg = backup_admin.save_config(
            self._backup_base_dir(),
            self.bk_gmail.get(), self.bk_apppw.get(),
            self.bk_auto_var.get())
        self._backup_show_status(cfg)

    def _backup_send_thread(self):
        base = self._backup_base_dir()
        cfg = backup_admin.load_config(base)
        rkey = users.get_meta("recovery_key")
        ok, msg = backup_admin.send_backup(
            cfg.get("gmail", ""), cfg.get("app_password", ""),
            os.path.join(base, "users.db"), recovery_key=rkey)
        if ok:
            backup_admin.mark_backed_up(base)
        self.after(0, lambda: self._backup_send_done(ok, msg))

    def _backup_send_done(self, ok, msg):
        cfg = backup_admin.load_config(self._backup_base_dir())
        self._backup_show_status(cfg)
        self.log(f"Backup email: {msg}")
        if ok:
            messagebox.showinfo("Backup", msg, parent=self)
        else:
            messagebox.showerror("Backup", msg, parent=self)

    def _backup_auto_check(self):
        """Tool khulne par: 24 ghante guzar gaye hon to khud backup bhejo."""
        base = self._backup_base_dir()
        cfg = backup_admin.load_config(base)
        if backup_admin.needs_backup(cfg):
            self.log("Auto backup bheja ja raha hai...")
            threading.Thread(target=self._backup_send_thread,
                             daemon=True).start()

    def _backup_help(self):
        messagebox.showinfo(
            "App Password kaise banayein",
            "Gmail seedha password se login nahi karne deta. Ye karo:\n\n"
            "1. Phone/browser me myaccount.google.com kholo\n"
            "2. Security -> 2-Step Verification ON karo\n"
            "3. Usi page par 'App passwords' kholo\n"
            "4. App: 'Mail' select karo -> Generate dabao\n"
            "5. 16 harf wala password COPY karo (space hata kar)\n"
            "6. Yahan Gmail + wo password dal kar 'Save karo' dabao\n\n"
            "Ye password sirf is PC par save hota hai, kahin upload nahi hota.",
            parent=self)

    # ------------------- Gmail se backup wapis lao -------------------
    def _backup_restore_button(self):
        if self._backup_restore_flow(self):
            messagebox.showinfo("Restore",
                                "Tool ab band ho raha hai -- dobara kholo aur "
                                "apne purane admin se login karo.",
                                parent=self)
            self.destroy()

    def _backup_restore_flow(self, parent):
        """Gmail se latest users.db lao. Returns True agar restore hua."""
        base = self._backup_base_dir()
        cfg = backup_admin.load_config(base)
        dlg = tk.Toplevel(parent)
        dlg.title("Gmail se backup wapis lao")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        self._center_dialog(dlg, 420, 300)
        dlg.transient(parent)
        dlg.grab_set()

        tk.Label(dlg, text="Gmail se backup wapis lao", bg=BG, fg=TEAL,
                 font=("Arial", 14, "bold")).pack(pady=(18, 4))
        tk.Label(dlg, text="Jis Gmail par backup jata tha, wahi dalo.",
                 bg=BG, fg=MUTED, font=("Arial", 10)).pack(pady=(0, 10))
        frm = tk.Frame(dlg, bg=BG)
        frm.pack(padx=30, fill="x")
        tk.Label(frm, text="Gmail:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w",
                                                  pady=4)
        gmail_e = tk.Entry(frm, bg=PANEL, fg=FG, insertbackground=FG, width=28,
                           relief="flat", highlightthickness=1,
                           highlightbackground="#3a3a55", font=("Arial", 11))
        gmail_e.grid(row=0, column=1, pady=4, padx=6)
        gmail_e.insert(0, cfg.get("gmail", ""))
        tk.Label(frm, text="App Password:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w",
                                                  pady=4)
        pw_e = tk.Entry(frm, bg=PANEL, fg=FG, insertbackground=FG, width=28,
                        show="*", relief="flat", highlightthickness=1,
                        highlightbackground="#3a3a55", font=("Arial", 11))
        pw_e.grid(row=1, column=1, pady=4, padx=6)
        pw_e.insert(0, cfg.get("app_password", ""))
        status_lbl = tk.Label(dlg, text="", bg=BG, fg=MUTED,
                              font=("Arial", 9))
        status_lbl.pack(pady=4)

        result = {}

        def do_fetch():
            gmail = gmail_e.get().strip()
            pw = pw_e.get().replace(" ", "")
            if not gmail or not pw:
                messagebox.showerror("Error",
                                     "Gmail aur App Password dono dalo.",
                                     parent=dlg)
                return
            # taake agli dafa backup bhi isi Gmail par jaye
            backup_admin.save_config(base, gmail, pw, cfg.get("auto", False))
            status_lbl.config(text="Gmail se backup dhoonda ja raha hai... "
                                   "(thoda waqt lag sakta hai)")
            for w in (gmail_e, pw_e):
                w.config(state="disabled")
            threading.Thread(
                target=self._restore_thread,
                args=(base, gmail, pw, dlg, result, status_lbl),
                daemon=True).start()

        brow = tk.Frame(dlg, bg=BG)
        brow.pack(pady=12)
        self._btn(brow, "Backup lao", do_fetch, bg=TEAL).pack(side="left",
                                                              padx=6)
        self._btn(brow, "Cancel", dlg.destroy, bg=CARD, fg=FG).pack(
            side="left", padx=6)
        self.wait_window(dlg)
        return result.get("ok", False)

    def _restore_thread(self, base, gmail, pw, dlg, result, status_lbl):
        ok, msg, db_bytes = backup_admin.fetch_latest_backup(gmail, pw)
        self.after(0, lambda: self._restore_fetched(
            ok, msg, db_bytes, base, dlg, result, status_lbl))

    def _restore_fetched(self, ok, msg, db_bytes, base, dlg, result,
                         status_lbl):
        status_lbl.config(text="")
        if not ok:
            messagebox.showerror("Restore", msg, parent=dlg)
            return
        if not messagebox.askyesno(
                "Confirm",
                "Gmail wala backup mil gaya!\n\n"
                "users.db replace ho jayegi (maujooda ki safety copy ban "
                "jayegi).\nJari rakho?",
                parent=dlg):
            return
        ok2, msg2 = backup_admin.restore_db(base, db_bytes)
        if ok2:
            messagebox.showinfo("Restore", msg2, parent=dlg)
            result["ok"] = True
            try:
                dlg.destroy()
            except Exception:
                pass
        else:
            messagebox.showerror("Restore", msg2, parent=dlg)

    # ------------------- recovery key dikhao -------------------
    def _recovery_key_show(self):
        key = users.get_meta("recovery_key")
        if not key:
            if not messagebox.askyesno(
                    "Recovery key",
                    "Koi recovery key nahi mili (purana version se upgrade).\n"
                    "Nayi master recovery key banau?",
                    parent=self):
                return
            key = recovery.generate_key()
            users.set_meta("recovery_key", key)
            self.log("Nayi master recovery key banayi gayi.")
        self._show_recovery_key_once(key, first_time=False)

    # ------------------------- log + status bar -------------------------
    def _log_area(self):
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=10)
        tk.Label(row, text="Log:", bg=BG, fg=MUTED,
                 font=("Arial", 10, "bold")).pack(side="left")
        self._btn(row, "Save Log", self._save_log,
                  bg=CARD, fg=FG).pack(side="right", padx=3)
        self._btn(row, "Clear", self._clear_log,
                  bg=CARD, fg=FG).pack(side="right")
        self.log_text = self._dark_text(self, 6)
        self.log_text.configure(state="disabled")
        self.log_text.pack(fill="x", padx=10, pady=(0, 6))

    def _save_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            initialfile="gsmtool-log.txt",
            title="Log save karo")
        if not path:
            return
        self.log_text.configure(state="normal")
        content = self.log_text.get("1.0", "end")
        self.log_text.configure(state="disabled")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            self.log(f"Log save ho gaya: {path}")
        except OSError as exc:
            messagebox.showerror("Save Log", f"Save nahi hua: {exc}")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _status_bar(self):
        bar = tk.Frame(self, bg=CARD, height=26)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        tk.Label(bar, textvariable=self.status_var, bg=CARD, fg=MUTED,
                 font=("Arial", 9)).pack(side="left", padx=10)

    def _update_status(self):
        adb_ok = "OK" if self.adb else "MISSING"
        fb_ok = "OK" if self.fb else "MISSING"
        who = ""
        if self.current_user:
            role = "Admin" if self.current_is_admin else "User"
            exp = getattr(self, "current_expiry", None)
            exp_txt = f", {users.fmt_expiry(exp)}" if not self.current_is_admin else ""
            who = f"Logged in: {self.current_user} ({role}{exp_txt})   |   "
        self.status_var.set(f"{who}adb: {adb_ok}   |   fastboot: {fb_ok}   |   Hamza GSM Tool v{__version__}")

    # ------------------------- drivers tab -------------------------
    def _build_drivers_tab(self):
        tk.Label(self.tab_drivers,
                 text="Drivers -- phone detect na ho to sab se pehle ye dekho.",
                 bg=BG, fg=FG, font=("Arial", 12, "bold")).pack(anchor="w",
                                                               padx=12, pady=(10, 2))
        brow = tk.Frame(self.tab_drivers, bg=BG)
        brow.pack(fill="x", padx=12, pady=6)
        self._btn(brow, "Check Installed Drivers",
                  lambda: self._run_bg(
                      "driver check",
                      lambda: drivers.check_drivers(self.adb, self.fb))
                  ).pack(side="left", padx=3)
        self._btn(brow, "Install Driver from Folder…",
                  self._driver_install_pick,
                  bg=CARD, fg=FG).pack(side="left", padx=3)
        tk.Label(self.tab_drivers,
                 text="Driver list (official = verified official page; "
                      "bundled = flashing tool package ke sath milta hai):",
                 bg=BG, fg=MUTED, font=("Arial", 10)).pack(anchor="w",
                                                          padx=12, pady=(4, 2))
        for name, purpose, url, kind, note in drivers.DRIVER_ROWS:
            row = tk.Frame(self.tab_drivers, bg=PANEL)
            row.pack(fill="x", padx=12, pady=3)
            tk.Label(row, text=name, bg=PANEL, fg=FG,
                     font=("Arial", 10, "bold"), width=30,
                     anchor="w").pack(side="left", padx=8, pady=6)
            tk.Label(row, text=purpose, bg=PANEL, fg=MUTED,
                     font=("Arial", 9), wraplength=400,
                     justify="left").pack(side="left", padx=4)
            if kind == "official" and url:
                self._btn(row, "Download ↗",
                          lambda u=url: webbrowser.open(u),
                          bg=TEAL).pack(side="right", padx=8)
            else:
                self._btn(row, "Info",
                          lambda n=note, t=name: messagebox.showinfo(t, n),
                          bg=CARD, fg=FG).pack(side="right", padx=8)

    def _driver_install_pick(self):
        folder = filedialog.askdirectory(
            title="Driver folder select karo (.inf files)")
        if folder:
            self._run_bg("driver install",
                         lambda: drivers.install_driver_folder(folder))

    # ------------------------- test point / edl tab -------------------------
    def _build_edl_tab(self):
        tk.Label(self.tab_edl,
                 text="EDL / BROM / Download Mode -- brand ka safe tareeqa dekho.",
                 bg=BG, fg=FG, font=("Arial", 12, "bold")).pack(anchor="w",
                                                               padx=12, pady=(10, 2))
        tk.Label(self.tab_edl,
                 text="WARNING: test point har MODEL ka alag hota hai (brand ka "
                      "nahi). Ghalat point short karne se board DEAD ho sakta hai!",
                 bg=WARN_BG, fg="#ffd9d9", font=("Arial", 10, "bold"),
                 wraplength=880, justify="left",
                 padx=8, pady=6).pack(fill="x", padx=12, pady=6)
        brow = tk.Frame(self.tab_edl, bg=BG)
        brow.pack(fill="x", padx=12, pady=4)
        tk.Label(brow, text="Brand:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).pack(side="left")
        self.edl_brand_var = tk.StringVar()
        names = [n for _, _, n, _, _ in BRAND_TILES]
        cb = ttk.Combobox(brow, textvariable=self.edl_brand_var,
                          values=names, state="readonly", width=18,
                          font=("Arial", 10))
        cb.pack(side="left", padx=8)
        cb.current(0)
        self._btn(brow, "Show Method",
                  self._show_edl_brand).pack(side="left", padx=3)
        self._btn(brow, "FRP Notes",
                  lambda: self._edl_show(edl.FRP_NOTES),
                  bg=CARD, fg=FG).pack(side="left", padx=3)
        srow = tk.Frame(self.tab_edl, bg=BG)
        srow.pack(fill="x", padx=12, pady=4)
        tk.Label(srow, text="Model (test point search):", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).pack(side="left")
        self.edl_model_var = tk.StringVar(value="X6887")
        tk.Entry(srow, textvariable=self.edl_model_var, width=22, bg=PANEL,
                 fg=FG, insertbackground=FG, relief="flat",
                 highlightthickness=1, highlightbackground="#3a3a55",
                 font=("Arial", 10)).pack(side="left", padx=8)
        self._btn(srow, "Search Test Point",
                  self._search_testpoint, bg=TEAL).pack(side="left", padx=3)
        self.edl_text = self._dark_text(self.tab_edl, 13)
        self.edl_text.pack(fill="both", expand=True, padx=12, pady=4)
        self.edl_text.insert("end", edl.TESTPOINT_WARNINGS + "\n")

    def _edl_show(self, text):
        self.edl_text.delete("1.0", "end")
        self.edl_text.insert("end", text + "\n")

    def _show_edl_brand(self):
        name = self.edl_brand_var.get()
        key = next((k for k, _, n, _, _ in BRAND_TILES if n == name), None)
        self._edl_show("=== " + name + " ===\n"
                       + edl.brand_edl_text(key) + "\n"
                       + edl.TESTPOINT_WARNINGS)

    def _search_testpoint(self):
        model = self.edl_model_var.get().strip()
        if not model:
            messagebox.showwarning("Model", "Pehle model likho (misal: X6887).")
            return
        webbrowser.open(edl.testpoint_search_url(model))
        self.log(f"Test point search khola: {model}")

    # ------------------------- backup tab -------------------------
    def _build_backup_tab(self):
        tk.Label(self.tab_backup,
                 text="Backup -- flashing se PEHLE backup lo!",
                 bg=BG, fg=FG, font=("Arial", 12, "bold")).pack(anchor="w",
                                                               padx=12, pady=(10, 2))
        tk.Label(self.tab_backup,
                 text="NVRAM / IMEI ka backup na ho to ghalti se data gaya to "
                      "wapis nahi aayega. Ye aadat banao.",
                 bg=WARN_BG, fg="#ffd9d9", font=("Arial", 10, "bold"),
                 wraplength=880, justify="left",
                 padx=8, pady=6).pack(fill="x", padx=12, pady=6)
        brow = tk.Frame(self.tab_backup, bg=BG)
        brow.pack(fill="x", padx=12, pady=8)
        self._btn(brow, "Backup Installed APKs",
                  self._backup_apks).pack(side="left", padx=3)
        self._btn(brow, "Save Device Report",
                  self._backup_report, bg=CARD, fg=FG).pack(side="left", padx=3)
        tk.Label(self.tab_backup,
                 text="Backups tool wali folder ke andar 'backups' me save hote hain.",
                 bg=BG, fg=MUTED, font=("Arial", 10)).pack(anchor="w",
                                                          padx=12, pady=4)

    def _backup_dir(self):
        here = paths.base_dir()
        folder = os.path.join(here, "backups", self._serial() or "default")
        os.makedirs(folder, exist_ok=True)
        return folder

    def _backup_apks(self):
        def job():
            if not self.adb:
                return "adb nahi mila -- pehle platform-tools set karo."
            base = ["-s", self._serial()] if self._serial() else []
            out = adbwrap.run(self.adb, base + ["shell", "pm", "list",
                                                "packages", "-3"])
            pkgs = [l.split(":", 1)[1].strip() for l in out.splitlines()
                    if l.startswith("package:")]
            if not pkgs:
                return "Koi user app nahi mili."
            folder = self._backup_dir()
            done, failed = 0, 0
            for pkg in pkgs:
                try:
                    pp = adbwrap.run(self.adb, base + ["shell", "pm", "path",
                                                      pkg])
                    apks = [l.split(":", 1)[1].strip()
                            for l in pp.splitlines()
                            if l.startswith("package:")]
                    for i, apk in enumerate(apks):
                        dest = os.path.join(folder, f"{pkg}_{i}.apk")
                        adbwrap.run(self.adb, base + ["pull", apk, dest])
                    done += 1
                except Exception:  # noqa: BLE001 - count, keep going
                    failed += 1
            msg = f"{done} apps backup ho gayin: {folder}"
            if failed:
                msg += f" ({failed} fail)"
            return msg
        self._run_bg("APK backup", job)

    def _backup_report(self):
        def job():
            if not self.adb:
                return "adb nahi mila -- pehle platform-tools set karo."
            base = ["-s", self._serial()] if self._serial() else []
            props = adbwrap.run(self.adb, base + ["shell", "getprop"])
            folder = self._backup_dir()
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            fname = f"device-report-{self._serial() or 'default'}-{stamp}.txt"
            path = os.path.join(folder, fname)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f"Hamza GSM Tool device report -- {stamp}\n\n")
                fh.write(props)
            return f"Report save ho gayi: {path}"
        self._run_bg("device report", job)

    # ------------------------- iphone tab -------------------------
    def _build_iphone_tab(self):
        tk.Label(self.tab_iphone,
                 text="iPhone -- Apple servicing section.",
                 bg=BG, fg=FG, font=("Arial", 12, "bold")).pack(anchor="w",
                                                               padx=12, pady=(10, 2))
        tk.Label(self.tab_iphone,
                 text="iPhone ADB/Fastboot par NAHI chalta -- Apple ke apne "
                      "protocols hain. Neeche wale buttons libimobiledevice "
                      "tools use karte hain (agar installed hon).",
                 bg=BG, fg=MUTED, font=("Arial", 10),
                 wraplength=900, justify="left").pack(anchor="w", padx=12,
                                                      pady=4)
        brow = tk.Frame(self.tab_iphone, bg=BG)
        brow.pack(fill="x", padx=12, pady=6)
        self._btn(brow, "Check Tools",
                  lambda: self._run_bg("iphone tools",
                                       iphone.check_tools)).pack(side="left",
                                                                 padx=3)
        self._btn(brow, "Detect iPhone",
                  lambda: self._run_bg("detect iphone",
                                       iphone.detect_iphone)).pack(side="left",
                                                                   padx=3)
        self._btn(brow, "Device Info",
                  lambda: self._run_bg("iphone info",
                                       iphone.device_info)).pack(side="left",
                                                                 padx=3)
        self._btn(brow, "Enter Recovery",
                  lambda: self._run_bg("enter recovery",
                                       iphone.enter_recovery),
                  bg=CARD, fg=FG).pack(side="left", padx=3)
        self._btn(brow, "Exit Recovery",
                  lambda: self._run_bg("exit recovery",
                                       iphone.exit_recovery),
                  bg=CARD, fg=FG).pack(side="left", padx=3)
        self._btn(brow, "iTunes Download",
                  lambda: webbrowser.open(iphone.ITUNES_URL),
                  bg=TEAL).pack(side="left", padx=3)
        drow = tk.Frame(self.tab_iphone, bg=BG)
        drow.pack(fill="x", padx=12, pady=4)
        tk.Label(drow, text="DFU Guide:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).pack(side="left")
        self.iphone_gen_var = tk.StringVar()
        gens = list(iphone.DFU_GUIDES.keys())
        cb = ttk.Combobox(drow, textvariable=self.iphone_gen_var,
                          values=gens, state="readonly", width=36,
                          font=("Arial", 10))
        cb.pack(side="left", padx=8)
        cb.current(0)
        self._btn(drow, "Show DFU Steps",
                  self._show_dfu).pack(side="left", padx=3)
        self._btn(drow, "Activation Lock Notes",
                  lambda: self._iphone_show(iphone.ACTIVATION_LOCK_NOTES),
                  bg=CARD, fg=FG).pack(side="left", padx=3)
        self.iphone_text = self._dark_text(self.tab_iphone, 11)
        self.iphone_text.pack(fill="both", expand=True, padx=12, pady=4)
        self.iphone_text.insert("end", "Upar buttons dabao -- tools check, "
                                      "detection, recovery, DFU guides.\n")
        # ---- iPhone model reference (A-numbers) ----
        mframe = tk.LabelFrame(self.tab_iphone, text="  iPhone Models (A-number)  ",
                               bg=BG, fg=FG, font=("Arial", 10, "bold"),
                               padx=8, pady=6)
        mframe.pack(fill="x", padx=12, pady=(4, 8))
        mrow = tk.Frame(mframe, bg=BG)
        mrow.pack(fill="x")
        tk.Label(mrow, text="Search:", bg=BG, fg=FG,
                 font=("Arial", 10)).pack(side="left")
        self.iphone_search_var = tk.StringVar()
        se = tk.Entry(mrow, textvariable=self.iphone_search_var, width=28,
                      bg=PANEL, fg=FG, insertbackground=FG, relief="flat",
                      highlightthickness=1, highlightbackground="#3a3a55",
                      font=("Arial", 10))
        se.pack(side="left", padx=8)
        self.iphone_model_list = tk.Listbox(mframe, height=5, bg=PANEL, fg=FG,
                                            selectbackground=ACCENT, relief="flat",
                                            highlightthickness=1,
                                            highlightbackground="#3a3a55",
                                            font=("Arial", 10))
        self.iphone_model_list.pack(fill="x", pady=(6, 0))
        self.iphone_search_var.trace_add(
            "write", lambda *_a: self._iphone_model_search())
        self._iphone_model_search()

    def _iphone_model_search(self):
        q = (self.iphone_search_var.get() or "").strip().lower()
        self.iphone_model_list.delete(0, "end")
        for m in models.search_models("apple", q):
            code = m["code"] or "--"
            self.iphone_model_list.insert(
                "end", f"{m['model']}  |  {code}  |  {m['chipset']}")

    def _iphone_show(self, text):
        self.iphone_text.delete("1.0", "end")
        self.iphone_text.insert("end", text + "\n")

    def _show_dfu(self):
        self._iphone_show(iphone.dfu_text(self.iphone_gen_var.get()))

    # ------------------------- publish update tab -------------------------
    def _build_release_tab(self):
        tk.Label(self.tab_release,
                 text="Publish Update -- ek click me nayi version live karo.",
                 bg=BG, fg=FG, font=("Arial", 12, "bold")).pack(anchor="w",
                                                               padx=12, pady=(10, 2))
        tk.Label(self.tab_release,
                 text=f"Current version: v{__version__}",
                 bg=BG, fg=MUTED, font=("Arial", 10)).pack(anchor="w",
                                                          padx=12, pady=2)
        frm = tk.Frame(self.tab_release, bg=BG)
        frm.pack(fill="x", padx=12, pady=8)
        tk.Label(frm, text="New version:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).pack(side="left")
        self.rel_ver_var = tk.StringVar(value="7.2")
        tk.Entry(frm, textvariable=self.rel_ver_var, width=10, bg=PANEL, fg=FG,
                 insertbackground=FG, relief="flat",
                 highlightthickness=1, highlightbackground="#3a3a55",
                 font=("Arial", 10)).pack(side="left", padx=8)
        self._btn(frm, "Auto +", self._bump_version,
                  bg=CARD, fg=FG).pack(side="left")
        tk.Label(frm, text="Kya naya hai:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).pack(side="left", padx=(12, 0))
        self.rel_notes_var = tk.StringVar()
        tk.Entry(frm, textvariable=self.rel_notes_var, width=36, bg=PANEL,
                 fg=FG, insertbackground=FG, relief="flat",
                 highlightthickness=1, highlightbackground="#3a3a55",
                 font=("Arial", 10)).pack(side="left", padx=8)

        # github token row (one-time setup)
        trow = tk.Frame(self.tab_release, bg=BG)
        trow.pack(fill="x", padx=12, pady=4)
        tk.Label(trow, text="GitHub Token:", bg=BG, fg=FG,
                 font=("Arial", 10, "bold")).pack(side="left")
        self.token_var = tk.StringVar()
        tk.Entry(trow, textvariable=self.token_var, width=30, bg=PANEL, fg=FG,
                 insertbackground=FG, relief="flat", show="\u2022",
                 highlightthickness=1, highlightbackground="#3a3a55",
                 font=("Arial", 10)).pack(side="left", padx=8)
        self._btn(trow, "Save Token", self._save_gh_token,
                  bg=CARD, fg=FG).pack(side="left", padx=3)
        self._btn(trow, "Token kaise banayen?",
                  lambda: messagebox.showinfo("GitHub Token",
                                              release.TOKEN_GUIDE),
                  bg=CARD, fg=FG).pack(side="left", padx=3)
        self.token_status_var = tk.StringVar()
        tk.Label(trow, textvariable=self.token_status_var, bg=BG, fg=TEAL,
                 font=("Arial", 9, "bold")).pack(side="left", padx=8)
        self._refresh_token_status()

        brow = tk.Frame(self.tab_release, bg=BG)
        brow.pack(fill="x", padx=12, pady=4)
        self._btn(brow, "PUBLISH TO GITHUB  (one click)",
                  self._publish_github, bg=TEAL).pack(side="left", padx=3)
        self._btn(brow, "Build Release Package",
                  self._build_release_pkg, bg=CARD, fg=FG).pack(side="left",
                                                               padx=3)
        self._btn(brow, "Open GitHub Upload Page",
                  self._open_upload_page, bg=CARD, fg=FG).pack(side="left",
                                                               padx=3)
        self.rel_text = self._dark_text(self.tab_release, 11)
        self.rel_text.pack(fill="both", expand=True, padx=12, pady=4)
        self.rel_text.insert(
            "end",
            "ONE-CLICK tareeqa:\n"
            "  1) Pehli dafa: 'Token kaise banayen?' parho, token banao, paste "
            "karke Save Token dabao.\n"
            "  2) Version likho (Auto + dabao to khud barh jayega), 'Kya naya "
            "hai' likho.\n"
            "  3) PUBLISH TO GITHUB dabao -- bas! Website 1-2 minute me update, "
            "tool khud sab ko update dega.\n"
            "Token sirf is PC par save hota hai, kisi ko mat dikhao.\n")

    def _refresh_token_status(self):
        if release.token_saved():
            self.token_status_var.set("Token saved hai \u2713")
        else:
            self.token_status_var.set("Token save nahi hai")

    def _save_gh_token(self):
        ok, msg = release.save_token(self.token_var.get())
        if ok:
            self.token_var.set("")
        self._refresh_token_status()
        messagebox.showinfo("GitHub Token", msg)

    def _bump_version(self):
        v = release.sanitize_version(__version__)
        parts = [int(x) for x in v.split(".") if x]
        while len(parts) < 2:
            parts.append(0)
        parts[1] += 1
        self.rel_ver_var.set(".".join(str(p) for p in parts[:2]))

    def _publish_github(self):
        ver = self.rel_ver_var.get()
        notes = self.rel_notes_var.get()
        if not self._confirm("Publish",
                             f"Version v{ver} GitHub par publish kar dun?\n"
                             "Website 1-2 minute me update ho jayegi."):
            return

        def job():
            def progress(m):
                self._jobs.put(m)
            ok, msg = release.publish_to_github(
                new_version=ver, notes=notes, progress=progress)
            return ("PUBLISH OK\n" + msg) if ok else ("PUBLISH FAILED\n" + msg)
        self._run_bg("publish to github", job)

    def _build_release_pkg(self):
        ver = self.rel_ver_var.get()
        notes = self.rel_notes_var.get()

        def job():
            ok, msg, _paths = release.build_release(new_version=ver,
                                                    notes=notes)
            return ("RELEASE OK\n" + msg) if ok else ("RELEASE FAILED\n" + msg)
        self._run_bg("build release", job)

    def _open_upload_page(self):
        url = release.github_upload_url(
            updater.load_config().get("update_url", ""))
        if url:
            webbrowser.open(url)
            self.log(f"Upload page khola: {url}")
        else:
            messagebox.showinfo(
                "Upload page",
                "Pehle \u2699 Update Settings me apni version.json wali site ka "
                "URL save karo.")

    # ------------------------------ widgets ------------------------------
    def _btn(self, parent, text, cmd, bg=ACCENT, fg="#ffffff"):
        return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                         activebackground="#8f7ff5", activeforeground="#ffffff",
                         relief="flat", padx=12, pady=6,
                         font=("Arial", 10, "bold"), cursor="hand2")

    def _dark_text(self, parent, height):
        return scrolledtext.ScrolledText(parent, height=height, bg=PANEL, fg=FG,
                                         insertbackground=FG,
                                         selectbackground=ACCENT, relief="flat",
                                         highlightthickness=1,
                                         highlightbackground="#3a3a55",
                                         font=("Arial", 10))

    # ------------------------------ helpers ------------------------------
    def log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll_jobs(self):
        try:
            while True:
                self.log(self._jobs.get_nowait())
        except queue.Empty:
            pass
        self.after(200, self._poll_jobs)

    def _run_bg(self, label, func):
        def worker():
            self._jobs.put(f">> {label}")
            try:
                out = func()
                if out:
                    self._jobs.put(str(out).strip()[:3000])
                self._jobs.put("done.")
            except Exception as exc:  # noqa: BLE001 - show in log
                self._jobs.put(f"ERROR: {exc}")
        threading.Thread(target=worker, daemon=True).start()

    def _serial(self):
        return self.serial.get().strip() or None

    def _confirm(self, title, msg):
        return messagebox.askyesno(title, msg)

    # ------------------------------ actions ------------------------------
    def _center(self, dlg):
        """Center a dialog over the main window (pretty on any screen)."""
        dlg.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - dlg.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _update_settings(self):
        """Let the user paste their own version.json URL (self-hosted updates)."""
        dlg = tk.Toplevel(self)
        dlg.title("Update Settings")
        dlg.configure(bg=BG)
        dlg.transient(self)
        dlg.grab_set()
        self._center(dlg)
        tk.Label(dlg, text="Apni website ka version.json link yahan paste karo:",
                 bg=BG, fg=FG, font=("Arial", 10, "bold"),
                 wraplength=420, justify="left").pack(padx=16, pady=(14, 6))
        tk.Label(dlg, text="Misal: https://tumhara-username.github.io/gsmtool/version.json",
                 bg=BG, fg=MUTED, font=("Arial", 9)).pack(padx=16)
        var = tk.StringVar(value=updater.load_config().get("update_url", ""))
        ent = tk.Entry(dlg, textvariable=var, width=52, bg=PANEL, fg=FG,
                       insertbackground=FG, relief="flat",
                       highlightthickness=1, highlightbackground="#3a3a55")
        ent.pack(padx=16, pady=10)

        def save():
            url = updater.save_update_url(var.get())
            self.log(f"Update URL set: {url or '(khali -- manual mode)'}")
            messagebox.showinfo("Update Settings",
                                "Save ho gaya!" + ("\nAb 'Check for Updates' dabao."
                                                   if url else ""),
                                parent=dlg)
            dlg.destroy()

        def test():
            updater.save_update_url(var.get())
            dlg.destroy()
            self._check_updates()

        brow = tk.Frame(dlg, bg=BG)
        brow.pack(pady=(0, 14))
        self._btn(brow, "Save", save).pack(side="left", padx=4)
        self._btn(brow, "Save + Test", test).pack(side="left", padx=4)
        self._btn(brow, "Cancel", dlg.destroy,
                  bg=CARD, fg=FG).pack(side="left", padx=4)

    def _check_updates(self):
        """'Check for Updates' button: honest update check, no fake promises."""
        self.log("Checking for updates...")
        status, msg, info = updater.check_for_updates()
        if status == "available":
            self.log(f"Update available: v{info.get('version')}")
            choice = self._update_choice_dialog(
                "Update available",
                msg + "\nKya karun?")
            if choice == "install":
                self._download_and_install(info)
            elif choice == "download":
                self._download_only(info)
        elif status == "uptodate":
            messagebox.showinfo("Updates", msg, parent=self)
        else:  # not_configured / error
            messagebox.showinfo("Updates", msg, parent=self)
        self.log(f"Update check: {status}")

    def _update_choice_dialog(self, title, msg):
        """Custom 3-button dialog. Returns 'install' | 'download' | None."""
        result = {"v": None}
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.configure(bg=BG)
        dlg.transient(self)
        dlg.grab_set()
        self._center(dlg)
        tk.Label(dlg, text=msg, bg=BG, fg=FG, font=("Arial", 10),
                 wraplength=400, justify="left").pack(padx=16, pady=12)
        brow = tk.Frame(dlg, bg=BG)
        brow.pack(pady=(0, 14))

        def pick(v):
            result["v"] = v
            dlg.destroy()

        self._btn(brow, "\u2b07 Install Now", lambda: pick("install")).pack(
            side="left", padx=4)
        self._btn(brow, "Download ZIP only", lambda: pick("download"),
                  bg=CARD, fg=FG).pack(side="left", padx=4)
        self._btn(brow, "Cancel", lambda: pick(None),
                  bg=CARD, fg=FG).pack(side="left", padx=4)
        self.wait_window(dlg)
        return result["v"]

    def _download_only(self, info):
        url = info.get("download_url", "")
        if not url:
            messagebox.showinfo("Update", "Download link set nahi hai.",
                                parent=self)
            return
        dest = os.path.join(paths.base_dir(),
                            f"HamzaGSMTool-v{info.get('version')}.zip")
        try:
            self.log(f"Downloading {url} ...")
            updater.download_update(url, dest)
            messagebox.showinfo("Update",
                                f"Download ho gaya:\n{dest}\n\n"
                                "UPDATE.bat chalao -- users.db mehfooz rahega.",
                                parent=self)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Update", f"Download fail:\n{exc}", parent=self)

    def _download_and_install(self, info):
        """One-click self-update: download, stage apply-script, restart."""
        url = info.get("download_url", "")
        if not url:
            messagebox.showinfo("Update", "Download link set nahi hai.",
                                parent=self)
            return
        app_dir = paths.base_dir()
        dest = os.path.join(app_dir, f"HamzaGSMTool-v{info.get('version')}.zip")
        try:
            self.log(f"Downloading {url} ...")
            updater.download_update(url, dest)
            script = updater.create_apply_script(app_dir, dest)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Update", f"Tayyari fail:\n{exc}", parent=self)
            return
        if not messagebox.askyesno(
                "Update",
                "Update download ho gaya.\n\n"
                "Ab tool band karke install shuru karun?\n"
                "Tumhare users/passwords mehfooz rahenge.",
                parent=self):
            return
        self.log("Applying update -- restarting...")
        try:
            os.startfile(script)  # Windows
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Update",
                f"Auto-install start nahi ho saka:\n{exc}\n\n"
                f"Manual: {script} chalao ya UPDATE.bat use karo.",
                parent=self)
            return
        self.destroy()

    def refresh(self):
        def job():
            lines = ["adb devices:"]
            for s, st in features.adb_devices(self.adb):
                lines.append(f"  {s}  [{st}]")
            lines.append("fastboot devices:")
            for s in features.fastboot_devices(self.fb):
                lines.append(f"  {s}")
            return "\n".join(lines)
        self._run_bg("refresh devices", job)

    def read_info(self):
        self._run_bg("read device info",
                     lambda: "\n".join(
                         f"{k}: {v}" for k, v in
                         features.device_info(self.adb, self._serial()).items()))

    def reboot(self, target):
        if not self._confirm("Reboot", f"Reboot device to '{target}'?"):
            return
        self._run_bg(f"reboot {target}",
                     lambda: features.reboot_device(self.adb, target, self._serial()))

    def scan_pkgs(self):
        def job():
            pkgs = features.list_packages(self.adb, self._serial())
            found = features.find_suspicious_packages(pkgs)
            self.pkg_list.delete(0, "end")
            for p in found or pkgs:
                self.pkg_list.insert("end", p)
            return (f"scanned {len(pkgs)} packages, "
                    f"{len(found)} MDM-like: {found or 'none'}")
        self._run_bg("scan packages", job)

    def show_admins(self):
        self._run_bg("device admins",
                     lambda: features.device_admins(self.adb, self._serial())
                     or "no active device admins")

    def pkg_action(self, what):
        sel = [self.pkg_list.get(i) for i in self.pkg_list.curselection()]
        if not sel:
            messagebox.showinfo("MDM tools", "Pehle list me se package select karo.")
            return
        if not self._confirm("Confirm",
                             f"{what.upper()} these packages?\n" + "\n".join(sel)):
            return

        def job():
            res = []
            for pkg in sel:
                if what == "disable":
                    features.disable_package(self.adb, pkg, self._serial())
                else:
                    features.uninstall_package(self.adb, pkg, self._serial())
                res.append(f"{what}d: {pkg}")
            return "\n".join(res)
        self._run_bg(f"{what} packages", job)

    # ---------------- MDM Easy Fix (3 steps) ----------------
    def _mdm_easy_check(self):
        def job():
            import adbwrap
            try:
                out = adbwrap.run(self.adb, ["devices"])
            except Exception as exc:
                return "ERR:" + str(exc)
            lines = [l for l in out.splitlines()[1:] if l.strip()]
            devs = [l for l in lines if "device" in l and "unauthorized" not in l]
            if devs:
                return f"OK:{len(devs)}"
            unauth = [l for l in lines if "unauthorized" in l]
            if unauth:
                return "UNAUTH:"
            return "NONE:"
        def done(res):
            if res.startswith("OK:"):
                n = res[3:]
                self.mdm_step1.config(text=f"1️⃣ ✅ Phone mil gaya ({n}) -- zabardast!",
                                      fg=TEAL)
                self.mdm_status.config(text="Ab step 2: MDM Scan karo.", fg=FG)
            elif res.startswith("UNAUTH:"):
                self.mdm_step1.config(text="1️⃣ ⚠️ Phone mila lekin 'unauthorized' -- "
                                           "phone par Allow/OK dabao, phir dobara check karo.",
                                      fg=WARN_BG)
            elif res.startswith("ERR:"):
                self.mdm_step1.config(text="1️⃣ ❌ adb nahi mila -- Drivers tab dekho.",
                                      fg=DANGER)
            else:
                self.mdm_step1.config(text="1️⃣ ❌ Phone nahi mila -- USB lagao, "
                                           "USB debugging ON karo, phir dobara check karo.",
                                      fg=DANGER)
            self.log("MDM easy check: " + res)
        self._run_bg_cb("mdm check", job, done)

    def _mdm_easy_scan(self):
        def job():
            pkgs = features.list_packages(self.adb, self._serial())
            found = features.find_suspicious_packages(pkgs)
            return pkgs, found
        def done(pair):
            pkgs, found = pair
            self._mdm_found = found or []
            self.pkg_list.delete(0, "end")
            for p in found or pkgs:
                self.pkg_list.insert("end", p)
            if found:
                for i in range(self.pkg_list.size()):
                    self.pkg_list.selection_set(i)
                self.mdm_step2.config(
                    text=f"2️⃣ ⚠️ {len(found)} MDM jaisi app(s) mili -- neeche list me select ho gayi hain.",
                    fg=WARN_BG)
                self.mdm_status.config(
                    text="Ab step 3: 'MDM FIX KARO' dabao -- sab ek saath disable ho jayengi.",
                    fg=FG)
            else:
                self.mdm_step2.config(text="2️⃣ ✅ Koi MDM app nahi mili -- phone saaf hai!",
                                      fg=TEAL)
                self.mdm_status.config(text="", fg=MUTED)
            self.log(f"MDM easy scan: {len(pkgs)} pkgs, {len(found)} MDM-like")
        self._run_bg_cb("mdm easy scan", job, done)

    def _mdm_easy_fix(self):
        found = self._mdm_found
        if not found:
            messagebox.showinfo("MDM Easy Fix",
                                "Pehle 'MDM Scan karo' dabao -- koi MDM app select nahi hai.",
                                parent=self)
            return
        if not self._confirm("MDM FIX KARO",
                             "Ye apps DISABLE ho jayengi (reversible -- wapis enable ho sakti hain):\n\n"
                             + "\n".join(found)
                             + "\n\nJari rakho?"):
            return
        def job():
            res = []
            for pkg in found:
                try:
                    features.disable_package(self.adb, pkg, self._serial())
                    res.append(f"disabled: {pkg}")
                except Exception as exc:
                    res.append(f"FAIL {pkg}: {exc}")
            return "\n".join(res)
        def done(out):
            self.mdm_step3.config(text="3️⃣ ✅ MDM Fix ho gaya! Phone restart karke check karo.",
                                  fg=TEAL)
            self.mdm_status.config(text="Note: disable reversible hai -- zaroorat ho to wapis enable kar sakte ho.",
                                   fg=MUTED)
            self._mdm_found = []
            self.log("MDM easy fix:\n" + out)
        self._run_bg_cb("mdm easy fix", job, done)

    def _run_bg_cb(self, name, job, done):
        """Background job with a done-callback on the UI thread."""
        def runner():
            try:
                res = job()
            except Exception as exc:
                self.after(0, lambda: self._bg_err(name, exc))
                return
            self.after(0, lambda: done(res))
        threading.Thread(target=runner, daemon=True).start()

    def _bg_err(self, name, exc):
        self.mdm_status.config(text=f"Error ({name}): {exc}", fg=DANGER)
        self.log(f"Error {name}: {exc}")

    def fb_devices(self):
        self._run_bg("fastboot devices",
                     lambda: features.fastboot_devices(self.fb) or "none")

    def fb_unlock(self):
        if not self._confirm("DANGER",
                             "Unlock bootloader? This WIPES all data and may "
                             "void warranty. Continue?"):
            return
        self._run_bg("bootloader unlock",
                     lambda: features.fastboot_unlock(self.fb, self._serial()))

    def fb_lock(self):
        if not self._confirm("Lock bootloader?",
                             "Only lock with STOCK firmware flashed, or the "
                             "phone may not boot. Continue?"):
            return
        self._run_bg("bootloader lock",
                     lambda: features.fastboot_lock(self.fb, self._serial()))

    def choose_image(self):
        path = filedialog.askopenfilename(title="Choose firmware image")
        if path:
            self.img_var.set(path)

    def fb_flash(self):
        part, img = self.part_var.get().strip(), self.img_var.get().strip()
        if not part or not img:
            messagebox.showinfo("Flash", "Partition aur image dono chahiye.")
            return
        if not self._confirm("DANGER",
                             f"Flash '{img}' to partition '{part}'?\n"
                             "Wrong image = bricked phone. Continue?"):
            return
        self._run_bg(f"flash {part}",
                     lambda: features.fastboot_flash(self.fb, part, img,
                                                     self._serial()))


if __name__ == "__main__":
    _stage("stage 7: starting ToolApp")
    _app = ToolApp()
    _stage("stage 8: entering mainloop")
    _app.mainloop()
