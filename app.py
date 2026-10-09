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
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

import adbwrap
import paths
import brands
import recovery
import drivers
import edl
import features
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
        ],
        "fastboot": [
            ("fb_check", "[FASTBOOT] Check Device"),
            ("fb_info", "[FASTBOOT] Read All Info"),
            ("frp_erase", "[FASTBOOT] Erase FRP"),
            ("frp_config", "[FASTBOOT] Erase Config (MTK)"),
            ("fb_wipe", "[FASTBOOT] Factory Reset (Wipe Data)"),
            ("fb_unlock", "[FASTBOOT] Unlock Bootloader"),
            ("fb_lock", "[FASTBOOT] Relock Bootloader"),
            ("fb_reboot", "[FASTBOOT] Reboot System"),
        ],
        "meta": [
            ("meta_boot", "[META] Boot to META Mode"),
            ("meta_imei", "[META] Restore Original IMEI"),
        ],
        "brom": [
            ("brom_frp", "[BROM] Erase FRP (MTK)"),
            ("edl_guide", "[EDL] Test Point Guide"),
        ],
        "tools": [
            ("drivers", "[TOOLS] Install Drivers"),
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
            # ---- FASTBOOT ----
            "fb_check": self._pro_fb_check,
            "fb_info": self._pro_fb_info,
            "frp_erase": self._pro_frp_erase,
            "frp_config": self._pro_frp_config,
            "fb_unlock": self._pro_fb_unlock,
            "fb_lock": self._pro_fb_lock,
            "fb_reboot": self._pro_fb_reboot,
            "fb_wipe": self._pro_fb_wipe,
            # ---- META ----
            "meta_boot": lambda: self.reboot("meta"),
            "meta_imei": self._pro_meta_imei,
            # ---- EDL/BROM ----
            "brom_frp": self._pro_brom_frp,
            "edl_guide": self._pro_edl_guide,
            # ---- TOOLS ----
            "drivers": self._pro_drivers,
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

    def _pro_brom_frp(self):
        """[BROM] Erase FRP (MTK): BROM device detect karo + guided erase.

        Seedhi baat: ye tool khud BROM flashing NAHI karta (uske liye SP Flash
        Tool / MTKClient + DA files darkar hain). Ye function device detect
        karke sahi, aazmaye hue steps deta hai -- koi fake "ho gaya" nahi.
        """
        if not self._confirm(
                "BROM FRP (MTK)",
                "MTK phone ka FRP BROM/PreLoader mode se erase hoga.\n\n"
                "Tareeqa:\n"
                "1. Phone BILKUL OFF karo (10 sec power dabao)\n"
                "2. Volume UP dabaye rakho + USB cable lagao\n"
                "3. 'MediaTek PreLoader USB VCOM' port aana chahiye\n\n"
                "Tool pehle port detect karega (60 sec wait), phir agle\n"
                "steps batayega. Asal erase SP Flash Tool / MTKClient\n"
                "se hota hai -- dono free hain.\n\n"
                "Sirf apne phone ya customer ki ijazat se karo.\n\n"
                "Jari rakho?"):
            return
        self._pro_set_status(
            "BROM device ka intezar... phone OFF karke Vol UP + USB lagao.",
            TEAL)

        def job():
            import time
            for _ in range(30):
                found, detail = features.detect_mtk_preloader()
                if found:
                    return "OK:" + detail
                time.sleep(2)
            return "NONE:60 second me koi MTK PreLoader/BROM device nahi mila"

        def done(res):
            if res.startswith("OK:"):
                self._pro_set_status(
                    "✅ BROM device mil gaya: " + res[3:], TEAL)
                self.log("BROM device detect ho gaya. Ab asal FRP erase "
                         "ke liye neeche guide follow karo:")
                self.log(features.BROM_FRP_GUIDE)
                self._pro_set_status(
                    "✅ BROM ready! Guide log me hai -- MTKClient/SP Flash "
                    "Tool se erase karo.", TEAL)
            else:
                self._pro_set_status("❌ " + res[5:], DANGER)
                self.log("Tip: Vol DOWN se try karo, ya cable/port badlo. "
                         "Device Manager me 'PreLoader' likha aana chahiye.")
        self._run_bg_cb("brom frp detect", job, done)

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

    def _pro_fb_wipe(self):
        if not self._confirm("Factory Reset",
                             "⚠️ WARNING: Phone ka SARA DATA delete ho jayega!\n"
                             "(Photos, contacts, apps -- sab kuch!)\n\n"
                             "Sirf apne phone ya customer ki ijazat se karo.\n\n"
                             "Jari rakho?"):
            return
        self._pro_set_status("Factory reset ho raha hai...", TEAL)

        def job():
            try:
                out1 = features.fastboot_erase(self.fb, "userdata",
                                               self._serial())
                try:
                    features.fastboot_erase(self.fb, "cache", self._serial())
                except Exception:
                    pass
                return "OK:" + str(out1)
            except Exception as exc:
                return "ERR:" + str(exc)

        def done(res):
            if res.startswith("OK:"):
                self._pro_set_status(
                    "✅ Factory reset ho gaya! Phone reboot hoga.", TEAL)
            else:
                self._pro_set_status("❌ " + res[4:], DANGER)
        self._run_bg_cb("fb wipe", job, done)

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

    def _pro_meta_imei(self):
        """[META] Restore Original IMEI -- SIRF box/sticker wala original!

        SAKHT RULES:
        - Koi random/new IMEI generate NAHI hota, na kabhi hoga.
        - Sirf tab use karo jab flashing ke baad IMEI null/invalid ho gaya ho
          aur ORIGINAL IMEI (box/sticker printed) maujood ho.
        - Doosra IMEI likhna PTA ke under ILLEGAL hai.
        """
        if not self._confirm(
                "IMEI RESTORE -- SAKHT WARNING",
                "Sirf phone ka ORIGINAL IMEI likho\n"
                "(jo BOX ya BACK-STICKER par PRINTED hai).\n\n"
                "NAHI karna:\n"
                "- Doosra / naya / random IMEI likhna = PTA ke under ILLEGAL!\n"
                "- Chori ke phone par IMEI change karna = JURM!\n\n"
                "HAN karna:\n"
                "- Flashing ke baad IMEI null/invalid ho gaya ho\n"
                "- Aur ORIGINAL IMEI ka saboot (box/sticker) tumhare paas ho\n\n"
                "Samajh gaye? Jari rakho?"):
            return
        imei = simpledialog.askstring(
            "Original IMEI",
            "Box / sticker wala 15-digit ORIGINAL IMEI likho:",
            parent=self)
        if not imei:
            return
        ok, clean_or_reason = features.validate_imei(imei)
        if not ok:
            self._pro_set_status(
                "❌ IMEI ghalat hai: " + clean_or_reason, DANGER)
            self.log("IMEI validate fail: " + clean_or_reason)
            return
        clean = clean_or_reason
        if not self._confirm(
                "Confirm karo",
                f"IMEI: {clean}\n\n"
                "Kya YEHI IMEI phone ke BOX ya STICKER par printed hai?\n"
                "(Ghalat bayani illegal hai!)"):
            return
        # Honest scope: asal write META mode me vendor tool se hota hai.
        # Ye tool validate + reboot + exact AT commands deta hai.
        cmd1, cmd2 = features.imei_at_commands(clean)
        self._pro_set_status(
            f"✅ IMEI valid hai: {clean}. META mode me bheja ja raha hai...",
            TEAL)
        self.log("=" * 50)
        self.log("ORIGINAL IMEI RESTORE -- steps:")
        self.log("1. Phone META mode me ja raha hai (adb reboot meta).")
        self.log("2. Modem META / Maui META tool kholo (alag se chahiye).")
        self.log("3. Ye AT commands chalao:")
        self.log(f"   SIM1: {cmd1}")
        self.log(f"   SIM2: {cmd2}   (agar dual SIM hai to)")
        self.log("4. Phone reboot karo, *#06# se verify karo.")
        self.log("Yaad rakho: SIRF original IMEI -- koi aur likhna illegal hai!")
        self.log("=" * 50)
        messagebox.showinfo(
            "IMEI Restore -- Steps",
            f"IMEI valid: {clean}\n\n"
            "1. Phone ab META mode me jayega\n"
            "2. Modem META tool me ye commands chalao:\n"
            f"     {cmd1}\n"
            f"     {cmd2}\n"
            "3. Reboot karke *#06# se verify karo\n\n"
            "Sirf ORIGINAL IMEI -- doosra likhna illegal hai!",
            parent=self)
        try:
            self.reboot("meta")
        except Exception as exc:  # noqa: BLE001 - adb na ho to guide hi kaafi
            self.log(f"META reboot nahi ho saka ({exc}) -- phone manually "
                     "META mode me le jao, commands upar log me hain.")

    def _pro_drivers(self):
        self._pro_set_status("Drivers check ho rahe hain...", TEAL)
        self._run_bg("driver check", drivers.check_drivers)


    # ================= END v8.0 PRO UI =================

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

if __name__ == "__main__":
    _stage("stage 7: starting ToolApp")
    _app = ToolApp()
    _stage("stage 8: entering mainloop")
    _app.mainloop()
