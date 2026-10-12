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
import brandpacks
import freetools
import recovery
import drivers
import edl
import features
import mtktool
import spdtool
import datool
import cpudb
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
    # ============ v8.2: professional-tool style flat operation list ============
    # Har operation: (fid, label, avail_method_name).
    # avail_* (True, "") ya (False, "Urdu wajah") deta hai.
    # Wajah ke saath DISABLE dikhao -- fake success kabhi nahi!
    OP_CATEGORIES = [
        ("CONNECTION", [
            ("conn_check", "🔌 Device Check (sab modes)", "avail_basic"),
            ("brom_connect", "[BROM] Connect (VID:PID check)", "avail_basic"),
            ("spd_connect", "[SPD] Connect (Unisoc detect)", "avail_basic"),
            ("read_info", "[ADB] Read Info", "avail_adb"),
        ]),
        ("REBOOT", [
            ("reboot_system", "↻ Reboot to System", "avail_adb"),
            ("reboot_recovery", "↻ Reboot to Recovery", "avail_adb"),
            ("reboot_fastboot", "↻ Reboot to Fastboot", "avail_adb"),
            ("reboot_meta", "↻ Reboot to META Mode", "avail_adb"),
            ("brom_reset", "↻ Reboot from BROM (mtk reset)", "avail_mtk"),
        ]),
        ("FRP", [
            ("frp_brom", "[BROM] Erase FRP (MTKClient)", "avail_mtk"),
            ("frp_erase", "[FASTBOOT] Erase FRP", "avail_fb"),
            ("frp_config", "[FASTBOOT] Erase Config (MTK)", "avail_fb"),
        ]),
        ("📱 TRANSSION FRP (Tecno/Infinix/Itel)", [
            ("frp_transsion_guide", "📖 Transsion FRP Guide (MTK+SPD)", "avail_basic"),
            ("frp_spd_dump", "[SPD] Erase FRP (spd_dump)", "avail_basic"),
        ]),
        ("FACTORY RESET", [
            ("wipe_brom", "[BROM] Factory Reset (MTKClient)", "avail_mtk"),
            ("fb_wipe", "[FASTBOOT] Factory Reset", "avail_fb"),
        ]),
        ("IMEI", [
            ("meta_imei", "[META] Restore Original IMEI", "avail_meta_imei"),
        ]),
        ("FLASH", [
            ("flash_part", "[BROM] Flash Partition (MTKClient)", "avail_mtk"),
            ("flash_fw", "[BROM] Flash Firmware (Scatter)", "avail_mtk"),
        ]),
        ("PARTITIONS", [
            ("part_gpt", "[BROM] Read Partition Table (GPT)", "avail_mtk"),
            ("part_read", "[BROM] Backup Partition (read)", "avail_mtk"),
        ]),
        ("SPD / UNISOC", [
            ("spd_frp", "[SPD] Erase FRP (spd_dump)", "avail_spd"),
            ("spd_wipe", "[SPD] Factory Reset (spd_dump)", "avail_spd"),
            ("spd_flash_pac", "[SPD] Flash PAC Firmware (guide)", "avail_spd"),
            ("spd_diag", "[SPD] Diag Mode (guide)", "avail_spd"),
        ]),
        ("DA DATABASE", [
            ("da_finder", "🔍 DA Auto-Finder", "avail_basic"),
        ]),
        ("BOOTLOADER", [
            ("fb_info", "[FASTBOOT] Read All Info", "avail_fb"),
            ("fb_unlock", "[FASTBOOT] Unlock Bootloader", "avail_fb"),
            ("fb_lock", "[FASTBOOT] Relock Bootloader", "avail_fb"),
        ]),
        ("🧹 DEBLOAT", [
            ("deb_samsung", "🧹 Samsung Bloatware Remove", "avail_adb"),
            ("deb_xiaomi", "🧹 Xiaomi Bloatware Remove", "avail_adb"),
            ("deb_oppo", "🧹 Oppo/Realme Bloatware Remove", "avail_adb"),
            ("deb_vivo", "🧹 Vivo Bloatware Remove", "avail_adb"),
            ("deb_transsion", "🧹 Infinix/Tecno Bloatware Remove", "avail_adb"),
            ("deb_restore", "↩️ Removed Apps Wapas Lao", "avail_adb"),
        ]),
        ("🚫 OTA BLOCK", [
            ("ota_block", "🚫 OTA Updates Block (auto-detect brand)", "avail_adb"),
            ("ota_unblock", "✅ OTA Updates Wapas On", "avail_adb"),
        ]),
        ("🏪 DEMO MODE", [
            ("demo_remove", "🏪 Retail Demo Mode Remove", "avail_adb"),
        ]),
        ("📞 DIALER CODES", [
            ("dial_codes", "📞 Dialer Codes Reference", "avail_basic"),
        ]),
        ("📖 BRAND GUIDES", [
            ("guide_samsung", "📖 Samsung Guide (Odin/FRP/KG)", "avail_basic"),
            ("guide_xiaomi", "📖 Xiaomi Guide (EDL/Mi Acc)", "avail_basic"),
            ("guide_oppo", "📖 Oppo/Realme Guide", "avail_basic"),
            ("guide_vivo", "📖 Vivo Guide", "avail_basic"),
            ("guide_transsion", "📖 Infinix/Tecno Guide", "avail_basic"),
            ("guide_iphone", "📖 iPhone Guide (honest)", "avail_basic"),
        ]),
        ("🛠️ ADB TOOLS", [
            ("adb_screenshot", "📸 Screenshot Lo", "avail_adb"),
            ("adb_pullapk", "📦 Kisi App ka APK Nikalo", "avail_adb"),
            ("adb_backup", "💾 Full Backup (adb backup)", "avail_adb"),
            ("adb_wifi", "📶 Wireless ADB On Karo", "avail_adb"),
            ("scrcpy", "🖥️ Screen Mirror (scrcpy)", "avail_adb"),
        ]),
        ("📥 FREE TOOLS", [
            ("ft_samfw", "📥 SamFw FRP Tool (Samsung)", "avail_basic"),
            ("ft_odin", "📥 Odin3 (Samsung Flash)", "avail_basic"),
            ("ft_3utools", "📥 3uTools (iPhone)", "avail_basic"),
            ("ft_scrcpy", "📥 scrcpy (Screen Mirror)", "avail_basic"),
            ("ft_miflash", "📥 MiFlash (Xiaomi)", "avail_basic"),
            ("ft_frija", "📥 Frija (Samsung Firmware DL)", "avail_basic"),
            ("ft_realmeflash", "📥 Realme Flash Tool", "avail_basic"),
            ("ft_qpst", "📥 QFIL (Qualcomm EDL)", "avail_basic"),
            ("ft_androidwintool", "📥 Android Win Tool (Anti-Crack FREE)", "avail_basic"),
            ("ft_mtkclient_gui", "📥 MTKClient GUI (MTK FREE)", "avail_basic"),
            ("ft_spflashtool", "📥 SP Flash Tool (MTK)", "avail_basic"),
            ("ft_egsmtool", "📥 E-GSM Tool (1-Month Trial)", "avail_basic"),
            ("ft_mtkclient", "📥 mtkclient (Open-Source MTK)", "avail_basic"),
            ("ft_spflashtool_official", "📥 SP Flash Tool (Official)", "avail_basic"),
            ("ft_sfdtool", "📥 SFD Tool (SPD FREE)", "avail_basic"),
            ("ft_spdresearch", "📥 SPD Research Tool (Official)", "avail_basic"),
            ("ft_edl_qc", "📥 edl (Qualcomm Open-Source)", "avail_basic"),
            ("ft_miunlock", "📥 Mi Unlock (Official Xiaomi)", "avail_basic"),
            ("ft_modemmeta", "📥 ModemMeta (IMEI Restore MTK)", "avail_basic"),
            ("ft_snwriter", "📥 SN Writer (MTK Official)", "avail_basic"),
            ("ft_gstsamunlock", "📥 G-ST SamUnlock (Samsung)", "avail_basic"),
            ("ft_primetoolx", "📥 Prime Tool X (FRP)", "avail_basic"),
            ("ft_bmbtool", "📥 BMB Tool Pro (FRP)", "avail_basic"),
            ("ft_miketunlocker", "📥 Mike Techs Unlocker (35+ brands)", "avail_basic"),
            ("ft_oplus_edl", "📥 OPLUS EDL (Oppo/Realme/1+)", "avail_basic"),
            ("ft_carlcare_otp", "📥 Carlcare OTP (Transsion Server)", "avail_basic"),
            ("ft_transsion_mdm", "📥 Tecno/Infinix MDM Remove", "avail_basic"),
            ("ft_oumse_spd", "📥 OumseGsmToolPro (SPD)", "avail_basic"),
            ("ft_multiunlockmdm", "📥 MultiUnlockMDM (Transsion ID)", "avail_basic"),
            ("ft_halabtech_frp", "📥 HalabTech FRP (Samsung Latest)", "avail_basic"),
            ("ft_halabtech_v4", "📥 HalabTech Tool V4.0 (Samsung)", "avail_basic"),
            ("ft_samfw_v6", "📥 SamFw V6.0.1 (Latest)", "avail_basic"),
            ("ft_imeistar_frp", "📥 Samsung FRP (imeistar)", "avail_basic"),
            ("ft_phoenix_tool", "📥 Phoenix Tool (Transsion FRP FREE!)", "avail_basic"),
            ("ft_samfirm_aio", "📥 SamFirm A.I.O (FRP)", "avail_basic"),
            ("ft_oplusprologin", "📥 OPlusProLogin V6 (Transsion)", "avail_basic"),
            ("ft_mtk_cli", "📥 MTK CLI Tool (FRP)", "avail_basic"),
            ("ft_spd_frp_simple", "📥 Simple SPD FRP Tool", "avail_basic"),
        ]),
        ("🔒 ANTI-CRACK", [
            ("anticrack_check", "🔍 Anti-Crack Check (ADB)", "avail_adb"),
            ("anticrack_brom", "🔍 Anti-Crack Check (BROM/Lock)", "avail_basic"),
            ("anticrack_guide", "📖 Anti-Crack Fix Guide", "avail_basic"),
        ]),
        ("🆔 TRANSSION ID", [
            ("transid_check", "🆔 Transsion ID Check (ADB)", "avail_adb"),
            ("transid_guide", "📖 Transsion ID Remove Guide", "avail_basic"),
        ]),
        ("TOOLS", [
            ("mtk_install", "[TOOLS] Install MTKClient", "avail_basic"),
            ("spd_install", "[TOOLS] Install spd_dump (guide)", "avail_basic"),
            ("devmgr", "[TOOLS] Device Manager kholo", "avail_basic"),
            ("mdm_fix", "[ADB] MDM Scan & Fix", "avail_adb"),
            ("edl_guide", "📍 EDL Test Point Guide", "avail_basic"),
            ("drivers", "[TOOLS] Install Drivers", "avail_basic"),
        ]),
    ]

    def _build(self):
        """v8.2 layout: Brand -> Model -> Operation -> START (UnlockTool style)."""
        self._pro_state = {"brand": None, "op": None}
        self._pro_op_btns = {}
        self._pro_header()
        self._pro_brandbar()
        self._pro_main()
        self._pro_bottom()
        self._status_bar()
        self._pro_refresh_ops()
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
            # v8.6: poora brand name dikhao (user demand)
            b = tk.Button(inner, text=f"{badge} {name}", bg=color, fg=fg,
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
        self.pro_model_list.bind("<<ListboxSelect>>",
                                 self._pro_model_selected)
        self._pro_model_rows = []
        # right: operations (scrollable, categorized buttons)
        right = tk.Frame(main, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        oph = tk.Frame(right, bg=BG)
        oph.pack(fill="x")
        tk.Label(oph, text="Operations:", bg=BG, fg=MUTED,
                 font=("Arial", 10, "bold")).pack(side="left")
        self._btn(oph, "⟳", self._pro_refresh_ops,
                  bg=CARD, fg=FG).pack(side="right", padx=2)
        tk.Label(oph, text="refresh", bg=BG, fg=MUTED,
                 font=("Arial", 8)).pack(side="right")
        # scrollable canvas for op buttons
        self.pro_op_canvas = tk.Canvas(right, bg=BG, highlightthickness=0)
        op_scr = tk.Scrollbar(right, orient="vertical",
                              command=self.pro_op_canvas.yview)
        self.pro_op_canvas.configure(yscrollcommand=op_scr.set)
        op_scr.pack(side="right", fill="y")
        self.pro_op_canvas.pack(side="left", fill="both", expand=True, pady=4)
        self.pro_op_inner = tk.Frame(self.pro_op_canvas, bg=BG)
        self.pro_op_canvas.create_window((0, 0), window=self.pro_op_inner,
                                         anchor="nw")
        self.pro_op_inner.bind(
            "<Configure>",
            lambda _e: self.pro_op_canvas.configure(
                scrollregion=self.pro_op_canvas.bbox("all")))
        # status line
        self.op_status = tk.Label(right, text="Operation select karo, phir START dabao.",
                                  bg=BG, fg=MUTED, font=("Arial", 10),
                                  wraplength=700, justify="left")
        self.op_status.pack(anchor="w", pady=4)

    def _pro_refresh_models(self):
        q = (self.pro_search_var.get() or "").strip().lower()
        brand = self._pro_state["brand"]
        self.pro_model_list.delete(0, "end")
        self._pro_model_rows = []
        self._pro_state["model"] = None
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
            self._pro_model_rows.append(m)

    def _pro_model_selected(self, _event=None):
        sel = self.pro_model_list.curselection()
        if not sel or sel[0] >= len(self._pro_model_rows):
            self._pro_state["model"] = None
            return
        m = self._pro_model_rows[sel[0]]
        self._pro_state["model"] = m
        fam = cpudb.family_of(m.get("chipset", ""))
        fam_txt = cpudb.family_label(fam) if fam else "Unknown CPU"
        self.log(f"Model: {m.get('model')} -- CPU: {m.get('chipset', '?')} "
                 f"({fam_txt})")
        # CPU ke hisab se operations enable/disable dobara check karo
        self._pro_refresh_ops()
        self._pro_state["op"] = None
        self._pro_op_mark_selected()

    # ---------------- availability checks (v8.2) ----------------
    def avail_basic(self):
        return True, ""

    def avail_adb(self):
        if self.adb:
            return True, ""
        return False, "adb nahi mila -- platform-tools install karo (README dekho)"

    def avail_fb(self):
        if self.fb:
            return True, ""
        return False, "fastboot nahi mila -- platform-tools install karo"

    def avail_mtk(self):
        if not mtktool.find_mtk():
            return False, "MTKClient nahi hai -- [TOOLS] Install MTKClient chalao"
        return cpudb.op_allowed(self._selected_cpu_family(), "mtk")

    def avail_spd(self):
        if not spdtool.find_spd_dump():
            return False, ("spd_dump nahi mila -- [TOOLS] Install spd_dump "
                            "(guide) dekho")
        return cpudb.op_allowed(self._selected_cpu_family(), "spd")

    def avail_meta_imei(self):
        try:
            import serial  # noqa: F401
        except ImportError:
            return False, "pyserial nahi hai -- pip install pyserial chalao"
        return cpudb.op_allowed(self._selected_cpu_family(), "meta_imei")

    def _selected_cpu_family(self):
        """Selected model ka CPU family (mtk/spd/qcom/exynos/None)."""
        m = self._pro_state.get("model") or {}
        return cpudb.family_of(m.get("chipset", ""))

    # ---------------- operations panel ----------------
    def _pro_refresh_ops(self):
        for w in self.pro_op_inner.winfo_children():
            w.destroy()
        self._pro_op_btns = {}
        for cat, ops in self.OP_CATEGORIES:
            tk.Label(self.pro_op_inner, text=cat, bg=BG, fg=TEAL,
                     font=("Arial", 9, "bold")).pack(anchor="w", pady=(8, 2))
            for fid, label, avail_name in ops:
                ok, reason = getattr(self, avail_name)()
                if ok:
                    b = tk.Button(self.pro_op_inner, text="  " + label,
                                  bg=CARD, fg=FG, relief="flat",
                                  font=("Arial", 10), anchor="w", padx=8,
                                  pady=5, cursor="hand2",
                                  command=lambda f=fid: self._pro_op_select(f))
                else:
                    b = tk.Button(self.pro_op_inner,
                                  text="  🚫 " + label,
                                  bg="#2a2a3a", fg="#777788", relief="flat",
                                  font=("Arial", 10), anchor="w", padx=8,
                                  pady=5, cursor="hand2",
                                  command=lambda f=fid, r=reason:
                                      self._pro_op_blocked(f, r))
                b.pack(fill="x", padx=2, pady=1)
                self._pro_op_btns[fid] = b
        self._pro_op_mark_selected()
        self.op_status.config(text="Operation select karo, phir START dabao.",
                              fg=MUTED)

    def _pro_op_select(self, fid):
        self._pro_state["op"] = fid
        self._pro_op_mark_selected()
        label = next((l for _c, ops in self.OP_CATEGORIES for f, l, _a in ops
                      if f == fid), fid)
        self.op_status.config(text=f"Selected: {label} -- START dabao.",
                              fg=FG)

    def _pro_op_blocked(self, fid, reason):
        label = next((l for _c, ops in self.OP_CATEGORIES for f, l, _a in ops
                      if f == fid), fid)
        msg = f"🚫 {label} abhi nahi chal sakta:\n{reason}"
        self.op_status.config(text=msg, fg=WARN_BG)
        self.log(msg)

    def _pro_op_mark_selected(self):
        sel = self._pro_state.get("op")
        for fid, b in self._pro_op_btns.items():
            if fid == sel and "🚫" not in b.cget("text"):
                b.config(bg=TEAL, fg="#ffffff")
            elif "🚫" not in b.cget("text"):
                b.config(bg=CARD, fg=FG)

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
        fid = self._pro_state.get("op")
        if not fid:
            self.op_status.config(text="Pehle koi operation select karo!",
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
            # ---- CONNECTION ----
            "conn_check": self._pro_conn_check,
            "brom_connect": self._pro_brom_connect,
            "spd_connect": self._pro_spd_connect,
            "read_info": self.read_info,
            # ---- REBOOT ----
            "reboot_system": lambda: self.reboot("system"),
            "reboot_recovery": lambda: self.reboot("recovery"),
            "reboot_fastboot": lambda: self.reboot("fastboot"),
            "reboot_meta": self._pro_meta_boot,
            "brom_reset": self._pro_brom_reset,
            # ---- FRP ----
            "frp_brom": self._pro_frp_brom,
            "frp_erase": self._pro_frp_erase,
            "frp_config": self._pro_frp_config,
            "mdm_fix": self._pro_mdm_fix,
            # ---- FACTORY RESET ----
            "wipe_brom": self._pro_wipe_brom,
            "fb_wipe": self._pro_fb_wipe,
            # ---- IMEI ----
            "meta_imei": self._pro_meta_imei,
            # ---- FLASH ----
            "flash_part": self._pro_flash_part,
            "flash_fw": self._pro_flash_fw,
            # ---- PARTITIONS ----
            "part_gpt": self._pro_part_gpt,
            "part_read": self._pro_part_read,
            # ---- BOOTLOADER ----
            "fb_info": self._pro_fb_info,
            "fb_unlock": self._pro_fb_unlock,
            "fb_lock": self._pro_fb_lock,
            # ---- SPD ----
            "spd_frp": self._pro_spd_frp,
            "spd_wipe": self._pro_spd_wipe,
            "spd_flash_pac": self._pro_spd_flash_pac,
            "spd_diag": self._pro_spd_diag,
            # ---- DA ----
            "da_finder": self._pro_da_finder,
            # ---- TOOLS ----
            "mtk_install": self._pro_mtk_install,
            "spd_install": self._pro_spd_install,
            "devmgr": self._pro_devmgr,
            "mdm_fix": self._pro_mdm_fix,
            "edl_guide": self._pro_edl_guide,
            "drivers": self._pro_drivers,
            # ---- v8.3: DEBLOAT ----
            "deb_samsung": lambda: self._pro_debloat("Samsung"),
            "deb_xiaomi": lambda: self._pro_debloat("Xiaomi"),
            "deb_oppo": lambda: self._pro_debloat("Oppo / Realme"),
            "deb_vivo": lambda: self._pro_debloat("Vivo"),
            "deb_transsion": lambda: self._pro_debloat("Infinix / Tecno"),
            "deb_restore": self._pro_debloat_restore,
            # ---- v8.3: OTA ----
            "ota_block": self._pro_ota_block,
            "ota_unblock": self._pro_ota_unblock,
            # ---- v8.3: DEMO ----
            "demo_remove": self._pro_demo_remove,
            # ---- v8.3: DIALER ----
            "dial_codes": self._pro_dial_codes,
            # ---- v8.3: GUIDES ----
            "guide_samsung": lambda: self._pro_guide("Samsung"),
            "guide_xiaomi": lambda: self._pro_guide("Xiaomi"),
            "guide_oppo": lambda: self._pro_guide("Oppo / Realme"),
            "guide_vivo": lambda: self._pro_guide("Vivo"),
            "guide_transsion": lambda: self._pro_guide("Infinix / Tecno"),
            "guide_iphone": lambda: self._pro_guide("iPhone"),
            # ---- v8.3: ADB TOOLS ----
            "adb_screenshot": self._pro_adb_screenshot,
            "adb_pullapk": self._pro_adb_pullapk,
            "adb_backup": self._pro_adb_backup,
            "adb_wifi": self._pro_adb_wifi,
            "scrcpy": self._pro_scrcpy,
            # ---- v8.3: FREE TOOLS ----
            "ft_samfw": lambda: self._pro_freetool("samfw"),
            "ft_odin": lambda: self._pro_freetool("odin"),
            "ft_3utools": lambda: self._pro_freetool("3utools"),
            "ft_scrcpy": lambda: self._pro_freetool("scrcpy"),
            "ft_miflash": lambda: self._pro_freetool("miflash"),
            "ft_frija": lambda: self._pro_freetool("frija"),
            "ft_realmeflash": lambda: self._pro_freetool("realmeflash"),
            "ft_qpst": lambda: self._pro_freetool("qpst"),
            "ft_androidwintool": lambda: self._pro_freetool("androidwintool"),
            "ft_mtkclient_gui": lambda: self._pro_freetool("mtkclient_gui"),
            "ft_spflashtool": lambda: self._pro_freetool("spflashtool"),
            "ft_egsmtool": lambda: self._pro_freetool("egsmtool"),
            "ft_mtkclient": lambda: self._pro_freetool("mtkclient"),
            "ft_spflashtool_official": lambda: self._pro_freetool("spflashtool_official"),
            "ft_sfdtool": lambda: self._pro_freetool("sfdtool"),
            "ft_spdresearch": lambda: self._pro_freetool("spdresearch"),
            "ft_edl_qc": lambda: self._pro_freetool("edl_qc"),
            "ft_miunlock": lambda: self._pro_freetool("miunlock"),
            "ft_modemmeta": lambda: self._pro_freetool("modemmeta"),
            "ft_snwriter": lambda: self._pro_freetool("snwriter"),
            "ft_gstsamunlock": lambda: self._pro_freetool("gstsamunlock"),
            "ft_primetoolx": lambda: self._pro_freetool("primetoolx"),
            "ft_bmbtool": lambda: self._pro_freetool("bmbtool"),
            "ft_miketunlocker": lambda: self._pro_freetool("miketunlocker"),
            "ft_oplus_edl": lambda: self._pro_freetool("oplus_edl"),
            "ft_carlcare_otp": lambda: self._pro_freetool("carlcare_otp"),
            "ft_transsion_mdm": lambda: self._pro_freetool("transsion_mdm"),
            "ft_oumse_spd": lambda: self._pro_freetool("oumse_spd"),
            "ft_multiunlockmdm": lambda: self._pro_freetool("multiunlockmdm"),
            "ft_halabtech_frp": lambda: self._pro_freetool("halabtech_frp"),
            "ft_halabtech_v4": lambda: self._pro_freetool("halabtech_v4"),
            "ft_samfw_v6": lambda: self._pro_freetool("samfw_v6"),
            "ft_imeistar_frp": lambda: self._pro_freetool("imeistar_frp"),
            "ft_phoenix_tool": lambda: self._pro_freetool("phoenix_tool"),
            "ft_samfirm_aio": lambda: self._pro_freetool("samfirm_aio"),
            "ft_oplusprologin": lambda: self._pro_freetool("oplusprologin"),
            "ft_mtk_cli": lambda: self._pro_freetool("mtk_cli"),
            "ft_spd_frp_simple": lambda: self._pro_freetool("spd_frp_simple"),
            # ---- v8.4: ANTI-CRACK ----
            "anticrack_check": self._pro_anticrack_check,
            "anticrack_brom": self._pro_anticrack_brom,
            "anticrack_guide": self._pro_anticrack_guide,
            # ---- v8.5: TRANSSION ID ----
            "transid_check": self._pro_transid_check,
            "transid_guide": self._pro_transid_guide,
            # ---- v8.7: TRANSSION FRP ----
            "frp_transsion_guide": self._pro_frp_transsion_guide,
            "frp_spd_dump": self._pro_frp_spd_dump,
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

    # ================= v8.3: DEBLOAT =================
    def _pro_debloat(self, brand):
        """Brand ka safe bloatware per-user uninstall karo."""
        pkgs = brandpacks.BLOATWARE.get(brand, [])
        if not pkgs:
            self._pro_set_status("❌ Is brand ka pack nahi mila", DANGER)
            return
        self._pro_set_status(f"🧹 {brand}: {len(pkgs)} apps check ho rahi hain...", TEAL)

        def job():
            if not self.adb:
                return "ERR: adb nahi mila"
            try:
                installed = features.list_packages(self.adb, self._serial())
            except Exception as exc:
                return "ERR:" + str(exc)
            removed, skipped = [], []
            for pkg in pkgs:
                if pkg in brandpacks.NEVER_TOUCH:
                    skipped.append(pkg + " (protected)")
                    continue
                if pkg not in installed:
                    continue
                try:
                    features.uninstall_package(self.adb, pkg, self._serial())
                    removed.append(pkg)
                except Exception as exc:
                    skipped.append(f"{pkg} ({exc})")
            return f"OK:{len(removed)} removed|{len(skipped)} skipped|{','.join(removed[:8])}"

        def done(res):
            if res.startswith("OK:"):
                parts = res[3:].split("|")
                self._pro_set_status(f"✅ {parts[0]} apps remove, {parts[1]} skip", TEAL)
                self.log("Debloat removed: " + parts[2] if len(parts) > 2 else "")
            else:
                self._pro_set_status("❌ " + res[4:], DANGER)
        self._run_bg_cb("debloat", job, done)

    def _pro_debloat_restore(self):
        """Tamam brands ke removed apps wapas lao (install-existing)."""
        all_pkgs = []
        for plist in brandpacks.BLOATWARE.values():
            all_pkgs.extend(plist)
        self._pro_set_status("↩️ Apps restore ho rahi hain...", TEAL)

        def job():
            if not self.adb:
                return "ERR: adb nahi mila"
            ok = 0
            for pkg in dict.fromkeys(all_pkgs):
                try:
                    adbwrap.run(self.adb, ["shell", "cmd", "package",
                                           "install-existing", pkg] +
                                (["-s", self._serial()] if self._serial() else []))
                    ok += 1
                except Exception:
                    pass
            return f"OK:{ok} restore attempts"

        def done(res):
            self._pro_set_status("✅ " + res[3:] if res.startswith("OK:") else "❌ " + res[4:],
                                 TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb("debloat restore", job, done)

    # ================= v8.3: OTA =================
    def _detect_brand(self):
        """Connected phone ka brand detect karo (manufacturer prop se)."""
        try:
            out = adbwrap.run(self.adb, ["shell", "getprop", "ro.product.manufacturer"] +
                              (["-s", self._serial()] if self._serial() else [])).strip().lower()
        except Exception:
            return None
        if "samsung" in out:
            return "Samsung"
        if "xiaomi" in out or "redmi" in out or "poco" in out:
            return "Xiaomi"
        if "oppo" in out or "realme" in out or "oneplus" in out:
            return "Oppo / Realme"
        if "vivo" in out or "iqoo" in out:
            return "Vivo"
        if "infinix" in out or "tecno" in out or "itel" in out or "transsion" in out:
            return "Infinix / Tecno"
        return None

    def _pro_ota_block(self):
        brand = self._detect_brand() or "General"
        pkgs = brandpacks.OTA_PACKAGES.get(brand, []) + \
            ([] if brand == "General" else brandpacks.OTA_PACKAGES.get("General", []))
        self._pro_set_status(f"🚫 OTA block ({brand}): {len(pkgs)} packages...", TEAL)

        def job():
            if not self.adb:
                return "ERR: adb nahi mila"
            done_pkgs = []
            for pkg, method in pkgs:
                try:
                    if method == "disable":
                        features.disable_package(self.adb, pkg, self._serial())
                    else:
                        features.uninstall_package(self.adb, pkg, self._serial())
                    done_pkgs.append(pkg)
                except Exception:
                    pass
            return f"OK:{len(done_pkgs)} blocked ({brand})"

        def done(res):
            self._pro_set_status("✅ " + res[3:] if res.startswith("OK:") else "❌ " + res[4:],
                                 TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb("ota block", job, done)

    def _pro_ota_unblock(self):
        all_ota = []
        for plist in brandpacks.OTA_PACKAGES.values():
            all_ota.extend(p[0] for p in plist)
        self._pro_set_status("✅ OTA wapas on ho raha hai...", TEAL)

        def job():
            if not self.adb:
                return "ERR: adb nahi mila"
            ok = 0
            for pkg in dict.fromkeys(all_ota):
                try:
                    features.enable_package(self.adb, pkg, self._serial())
                    ok += 1
                except Exception:
                    pass
            return f"OK:{ok} OTA packages enabled"

        def done(res):
            self._pro_set_status("✅ " + res[3:] if res.startswith("OK:") else "❌ " + res[4:],
                                 TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb("ota unblock", job, done)

    # ================= v8.3: DEMO =================
    def _pro_demo_remove(self):
        self._pro_set_status("🏪 Demo mode remove ho raha hai...", TEAL)

        def job():
            if not self.adb:
                return "ERR: adb nahi mila"
            msgs = []
            # 1. systemui demo broadcast
            try:
                adbwrap.run(self.adb, ["shell", "am", "broadcast", "-a",
                                       "com.android.systemui.demo", "-e", "command", "exit"] +
                            (["-s", self._serial()] if self._serial() else []))
                msgs.append("demo broadcast sent")
            except Exception:
                pass
            # 2. demo packages uninstall
            try:
                installed = features.list_packages(self.adb, self._serial())
            except Exception as exc:
                return "ERR:" + str(exc)
            removed = []
            for pkg in brandpacks.DEMO_PACKAGES:
                if pkg in installed:
                    try:
                        features.uninstall_package(self.adb, pkg, self._serial())
                        removed.append(pkg)
                    except Exception:
                        pass
            # 3. retail codes hint
            return f"OK:broadcast ok, removed {len(removed)} demo apps. Samsung retail code pehle try karo: {', '.join(brandpacks.RETAIL_CODES)}"

        def done(res):
            self._pro_set_status("✅ " + res[3:] if res.startswith("OK:") else "❌ " + res[4:],
                                 TEAL if res.startswith("OK:") else DANGER)
            self.log(res)
        self._run_bg_cb("demo remove", job, done)

    # ================= v8.3: DIALER / GUIDES =================
    def _pro_dial_codes(self):
        win = tk.Toplevel(self.root)
        win.title("📞 Dialer Codes")
        win.geometry("520x560")
        txt = scrolledtext.ScrolledText(win, wrap=tk.WORD, font=("Consolas", 10))
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        out = ["📞 DIALER CODES (display only — auto-dial nahi hota)\n"]
        for brand, codes in brandpacks.DIALER_CODES.items():
            out.append(f"\n══ {brand} ══")
            for code, fn in codes:
                out.append(f"  {code}  →  {fn}")
        out.append("\n⚠️ *#*#7780#*#* / *2767*3855# kabhi dial mat karo (wipe!)")
        txt.insert(tk.END, "\n".join(out))
        txt.config(state=tk.DISABLED)

    def _pro_guide(self, brand):
        win = tk.Toplevel(self.root)
        win.title(f"📖 {brand} Guide")
        win.geometry("560x620")
        txt = scrolledtext.ScrolledText(win, wrap=tk.WORD, font=("Consolas", 10))
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        txt.insert(tk.END, brandpacks.BRAND_GUIDES.get(brand, "Guide nahi mili."))
        txt.config(state=tk.DISABLED)

    # ================= v8.3: ADB TOOLS =================
    def _pro_adb_screenshot(self):
        import datetime
        import subprocess
        fname = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(os.path.expanduser("~"), fname)
        self._pro_set_status("📸 Screenshot le raha hoon...", TEAL)

        def job():
            if not self.adb:
                return "ERR: adb nahi mila"
            try:
                s = ["-s", self._serial()] if self._serial() else []
                proc = subprocess.run([self.adb] + s + ["exec-out", "screencap", "-p"],
                                      capture_output=True, timeout=60)
                if proc.returncode != 0 or not proc.stdout:
                    return "ERR: screenshot failed"
                with open(path, "wb") as f:
                    f.write(proc.stdout)
                return f"OK:{path}"
            except Exception as exc:
                return "ERR:" + str(exc)

        def done(res):
            self._pro_set_status("✅ " + res[3:] if res.startswith("OK:") else "❌ " + res[4:],
                                 TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb("screenshot", job, done)

    def _pro_adb_pullapk(self):
        pkg = simpledialog.askstring("APK Nikalo", "Package name likho (jaise com.whatsapp):",
                                     parent=self.root)
        if not pkg:
            return
        pkg = pkg.strip()
        self._pro_set_status(f"📦 {pkg} ka APK nikal raha hoon...", TEAL)

        def job():
            if not self.adb:
                return "ERR: adb nahi mila"
            try:
                s = ["-s", self._serial()] if self._serial() else []
                p = adbwrap.run(self.adb, ["shell", "pm", "path", pkg] + s).strip()
                if not p.startswith("package:"):
                    return "ERR: package nahi mili"
                apk_path = p.split(":", 1)[1].strip()
                dest = os.path.join(os.path.expanduser("~"), f"{pkg}.apk")
                adbwrap.run(self.adb, ["pull", apk_path, dest] + s)
                return f"OK:{dest}"
            except Exception as exc:
                return "ERR:" + str(exc)

        def done(res):
            self._pro_set_status("✅ " + res[3:] if res.startswith("OK:") else "❌ " + res[4:],
                                 TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb("pull apk", job, done)

    def _pro_adb_backup(self):
        import datetime
        fname = f"backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.ab"
        dest = os.path.join(os.path.expanduser("~"), fname)
        if not messagebox.askyesno("Full Backup",
                                    "Phone par backup confirm karna hoga.\nShuru karen?",
                                    parent=self.root):
            return
        self._pro_set_status("💾 Backup shuru — phone par Allow dabao...", TEAL)

        def job():
            if not self.adb:
                return "ERR: adb nahi mila"
            try:
                s = ["-s", self._serial()] if self._serial() else []
                adbwrap.run(self.adb, ["backup", "-apk", "-shared", "-all", "-f", dest] + s,
                            timeout=1800)
                return f"OK:{dest}"
            except Exception as exc:
                return "ERR:" + str(exc)

        def done(res):
            self._pro_set_status("✅ " + res[3:] if res.startswith("OK:") else "❌ " + res[4:],
                                 TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb("adb backup", job, done)

    def _pro_adb_wifi(self):
        self._pro_set_status("📶 Wireless ADB on ho raha hai...", TEAL)

        def job():
            if not self.adb:
                return "ERR: adb nahi mila"
            try:
                s = ["-s", self._serial()] if self._serial() else []
                adbwrap.run(self.adb, ["tcpip", "5555"] + s)
                ip = adbwrap.run(self.adb, ["shell", "ip", "route"] + s)
                wifi_ip = ""
                for line in ip.splitlines():
                    if "src" in line:
                        parts = line.split()
                        try:
                            wifi_ip = parts[parts.index("src") + 1]
                            break
                        except Exception:
                            pass
                if wifi_ip:
                    return f"OK:adb connect {wifi_ip}:5555  (USB nikal sakte ho)"
                return "OK:tcpip 5555 on — adb connect <phone-ip>:5555 karo"
            except Exception as exc:
                return "ERR:" + str(exc)

        def done(res):
            self._pro_set_status("✅ " + res[3:] if res.startswith("OK:") else "❌ " + res[4:],
                                 TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb("wifi adb", job, done)

    def _pro_scrcpy(self):
        import subprocess, shutil
        exe = shutil.which("scrcpy") or freetools.find_tool_exe("scrcpy")
        if not exe:
            if messagebox.askyesno("scrcpy",
                                    "scrcpy nahi mila.\nDownload page kholon?",
                                    parent=self.root):
                webbrowser.open("https://github.com/Genymobile/scrcpy/releases")
            return
        try:
            s = ["-s", self._serial()] if self._serial() else []
            subprocess.Popen([exe] + s)
            self._pro_set_status("🖥️ scrcpy khul gaya", TEAL)
        except Exception as exc:
            self._pro_set_status(f"❌ scrcpy: {exc}", DANGER)

    # ================= v8.3: FREE TOOLS =================
    def _pro_freetool(self, key):
        info = freetools.FREE_TOOLS.get(key)
        if not info:
            return
        name, desc, url = info[0], info[1], info[2]
        exe = freetools.find_tool_exe(key)
        if exe:
            try:
                import subprocess
                subprocess.Popen([exe])
                self._pro_set_status(f"📥 {name} khul gaya", TEAL)
            except Exception as exc:
                self._pro_set_status(f"❌ {name}: {exc}", DANGER)
            return
        # v8.6: Auto-download agar direct URL hai
        if freetools.get_auto_dl_url(key):
            if messagebox.askyesno(name,
                                    f"{desc}\n\n{info[0]} abhi installed nahi hai.\n"
                                    f"OK dabao — tool KHUD download + install ho jayega!",
                                    parent=self.root):
                self._pro_freetool_autodl(key, name)
            return
        if messagebox.askyesno(name,
                                f"{desc}\n\n{freetools.tool_install_hint(key)}\n\nDownload page kholon?",
                                parent=self.root):
            webbrowser.open(url)

    def _pro_freetool_autodl(self, key, name):
        """Auto-download with progress dialog."""
        import tkinter.ttk as ttk
        dlg = tk.Toplevel(self.root)
        dlg.title(f"Download: {name}")
        dlg.configure(bg=BG)
        dlg.geometry("400x120")
        dlg.transient(self.root)
        tk.Label(dlg, text=f"📥 {name}\nDownload ho raha hai...",
                 bg=BG, fg=FG, font=("Arial", 10)).pack(pady=10)
        pb = ttk.Progressbar(dlg, length=300, mode='determinate')
        pb.pack(pady=10)
        lbl = tk.Label(dlg, text="0%", bg=BG, fg=FG)
        lbl.pack()

        def progress(pct):
            self.root.after(0, lambda: (pb.configure(value=pct), lbl.configure(text=f"{pct}%")))

        def job():
            return freetools.download_and_install(key, progress)

        def done(res):
            dlg.destroy()
            exe, err = res
            if exe:
                try:
                    import subprocess
                    subprocess.Popen([exe])
                    self._pro_set_status(f"✅ {name} install + khul gaya!", TEAL)
                    messagebox.showinfo(name, f"✅ {name} install ho gaya!\nAb se click karte hi khulega.", parent=self.root)
                except Exception as exc:
                    self._pro_set_status(f"❌ {name}: {exc}", DANGER)
            else:
                self._pro_set_status(f"❌ Download fail: {err}", DANGER)
                if messagebox.askyesno(name, f"Auto-download fail: {err}\n\nDownload page kholon?", parent=self.root):
                    import webbrowser
                    webbrowser.open(freetools.FREE_TOOLS[key][2])

        self._thread(job, done)

    # ================= v8.4: ANTI-CRACK =================
    def _pro_anticrack_check(self):
        """ADB mode: phone ON + USB debugging → anti-crack risk check."""
        self._pro_set_status("🔍 Anti-Crack Check: phone parh raha hoon...", TEAL)

        def job():
            if not self.adb:
                return "ERR: adb nahi mila"
            try:
                import anticrack
                # device info parho
                s = ["-s", self._serial()] if self._serial() else []
                model = adbwrap.run(self.adb, s + ["shell", "getprop", "ro.product.model"]).strip()
                brand = adbwrap.run(self.adb, s + ["shell", "getprop", "ro.product.brand"]).strip()
                ver = adbwrap.run(self.adb, s + ["shell", "getprop", "ro.build.version.release"]).strip()
                try:
                    aver = int(ver.split(".")[0])
                except Exception:
                    aver = 0
                if not model:
                    return "ERR: phone nahi mila (USB debugging ON karo)"
                risk, msg = anticrack.check_model(model, brand, aver)
                return f"OK:\n{msg}"
            except Exception as exc:
                return "ERR:" + str(exc)

        def done(res):
            if res.startswith("OK:"):
                messagebox.showinfo("🔍 Anti-Crack Check", res[3:], parent=self.root)
                self._pro_set_status("🔍 Anti-Crack Check complete", TEAL)
            else:
                self._pro_set_status(f"❌ {res}", DANGER)

        self._thread(job, done)

    def _pro_anticrack_brom(self):
        """BROM mode: lock phone bhi check ho — chip info se diagnose."""
        import anticrack
        msg = (
            "🔒 LOCK PHONE CHECK (BROM Mode)\n\n"
            "Phone OFF karo, phir:\n"
            "1. Vol UP + Vol DOWN dono dabao\n"
            "2. Dabay rakh kar USB lagao\n"
            "3. Device Manager me 'MTK USB Port' aana chahiye\n\n"
            "Phir OK dabao — tool chip read karke batayega\n"
            "ke anti-crack trigger hai ya koi aur masla."
        )
        if not messagebox.askokcancel("🔒 BROM Check", msg, parent=self.root):
            return
        self._pro_set_status("🔍 BROM: chip read ho raha hai...", TEAL)

        def job():
            try:
                import subprocess, shutil
                mtk = shutil.which("mtk") or shutil.which("mtk.py")
                if not mtk:
                    return ("INFO: mtkclient nahi mila.\n\n"
                            "[TOOLS] Install MTKClient se install karo,\n"
                            "phir dobara try karo.")
                r = subprocess.run([mtk, "printgpt"], capture_output=True,
                                   text=True, timeout=60)
                out = (r.stdout or "") + (r.stderr or "")
                state, dmsg = anticrack.brom_diagnose("", out)
                return f"OK:\n{dmsg}"
            except subprocess.TimeoutExpired:
                return "ERR: phone BROM me nahi mila (Vol buttons + USB try karo)"
            except Exception as exc:
                return "ERR:" + str(exc)

        def done(res):
            if res.startswith("OK:") or res.startswith("INFO:"):
                messagebox.showinfo("🔒 BROM Check", res[3:] if res.startswith("OK:") else res[5:], parent=self.root)
                self._pro_set_status("🔒 BROM Check complete", TEAL)
            else:
                self._pro_set_status(f"❌ {res}", DANGER)

        self._thread(job, done)

    def _pro_anticrack_guide(self):
        import anticrack
        messagebox.showinfo("📖 Anti-Crack Fix Guide", anticrack.fix_guide_urdu(), parent=self.root)
        self._pro_set_status("📖 Anti-Crack Guide dikhaya", TEAL)

    # ================= v8.5: TRANSSION ID =================
    def _pro_transid_check(self):
        """ADB: Transsion ID / account lock check karo."""
        self._pro_set_status("🆔 Transsion ID Check: phone parh raha hoon...", TEAL)

        # Transsion ID / account se related packages
        TRANSID_PKGS = [
            "com.transsion.id",
            "com.tecno.id",
            "com.infinix.id",
            "com.transsion.account",
            "com.carlcare",
        ]

        def job():
            if not self.adb:
                return "ERR: adb nahi mila"
            try:
                s = ["-s", self._serial()] if self._serial() else []
                pkgs = features.list_packages(self.adb, self._serial())
                found = [p for p in TRANSID_PKGS if any(p in x for x in pkgs)]
                model = adbwrap.run(self.adb, s + ["shell", "getprop", "ro.product.model"]).strip()
                if found:
                    return (f"OK:⚠️ TRANSSION ID MILA!\n\nModel: {model}\n"
                            f"Packages: {', '.join(found)}\n\n"
                            "Is phone par Transsion ID lock ho sakta hai.\n"
                            "📖 Transsion ID Remove Guide dekho.")
                return (f"OK:✅ Transsion ID nahi mila.\n\nModel: {model}\n"
                        "Koi ID lock package detect nahi hua.")
            except Exception as exc:
                return "ERR:" + str(exc)

        def done(res):
            if res.startswith("OK:"):
                messagebox.showinfo("🆔 Transsion ID Check", res[3:], parent=self.root)
                self._pro_set_status("🆔 Transsion ID Check complete", TEAL)
            else:
                self._pro_set_status(f"❌ {res}", DANGER)

        self._thread(job, done)

    def _pro_transid_guide(self):
        guide = """🆔 TRANSSION ID REMOVE GUIDE
(Tecno / Infinix / Itel Account Lock)

METHOD 1 — MDM Remove Tool (FREE, One-Click):
1. Free Tools → Tecno/Infinix MDM Remove Tool
2. Download: mobilerdx.com (password: mobilerdx.com)
3. Phone factory reset karo
4. Setup wizard par 4-5 tap → QR scanner khulega
5. Tool me QR Code ADB Enable → phone se scan karo
6. USB lagao → Remove MDM Lock dabao ✅

METHOD 2 — MultiUnlockMDM (Android 14/15/16):
1. Free Tools → MultiUnlockMDM
2. Video guide: youtube.com/watch?v=67-kFzLGFNw
3. Step by step follow karo

METHOD 3 — Carlcare OTP (Official Server):
1. Free Tools → Carlcare OTP Loader
2. Transsion ka official aftersales auth
3. VCOM/Preloader mode me OTP generate karo

⚠️ SIRF customer ke apne phone par!
Chori ka phone ho to kaam MAT karo."""
        messagebox.showinfo("📖 Transsion ID Guide", guide, parent=self.root)
        self._pro_set_status("📖 Transsion ID Guide dikhaya", TEAL)

    # ================= v8.7: TRANSSION FRP =================
    def _pro_frp_transsion_guide(self):
        guide = """📱 TRANSSION FRP REMOVE GUIDE
(Tecno / Infinix / Itel — MTK + SPD)

⭐ METHOD 1 — Phoenix Tool (FREE!):
1. Free Tools → Phoenix Service Tool
2. Free register karo (phoenixservicetool.com)
3. Transsion FRP bilkul FREE hai!
4. Android 13/14/15/16, MTK+SPD ✅

METHOD 2 — MTK phones (mtkclient):
1. Phone OFF → Vol buttons + USB (BROM mode)
2. Command: python mtk e frp
3. 100% free, open-source!

METHOD 3 — SPD phones (spd_dump):
1. [SPD] Erase FRP button dabao (neeche wala)
2. Ya SFD Tool GUI se partition erase

METHOD 4 — Android Win Tool:
1. Free Tools → Android Win Tool
2. FRP bypass (free tier)

METHOD 5 — QR Code (bina PC):
1. Free Tools → MDM Remove Tool
2. QR generate → setup wizard me scan
3. ADB on → FRP bypass

⚠️ Talkback method Android 14+ par patched hai!"""
        messagebox.showinfo("📖 Transsion FRP Guide", guide, parent=self.root)
        self._pro_set_status("📖 Transsion FRP Guide dikhaya", TEAL)

    def _pro_frp_spd_dump(self):
        """SPD: spd_dump se FRP erase."""
        msg = ("[SPD] FRP Erase\n\n"
               "1. spd_dump tool chahiye (Free Tools → SFD Tool)\n"
               "2. Phone OFF karo\n"
               "3. Vol UP+DOWN daba kar USB lagao\n"
               "4. OK dabao")
        if not messagebox.askokcancel("SPD FRP", msg, parent=self.root):
            return
        self._pro_set_status("SPD FRP: erase ho raha hai...", TEAL)

        def job():
            try:
                import subprocess, shutil
                spd = shutil.which("spd_dump")
                if not spd:
                    return ("INFO:spd_dump nahi mila.\nFree Tools → SFD Tool download karo.")
                # Generic FRP erase (FDL files phone-specific hote hain)
                return ("INFO:spd_dump mil gaya!\n\n"
                        "Phone-specific FDL1/FDL2 files chahiye.\n"
                        "SFD Tool GUI use karo (asan hai).")
            except Exception as exc:
                return "ERR:" + str(exc)

        def done(res):
            if res.startswith("INFO:"):
                messagebox.showinfo("SPD FRP", res[5:], parent=self.root)
            else:
                self._pro_set_status(f"❌ {res}", DANGER)
            self._pro_set_status("SPD FRP check complete", TEAL)

        self._run_bg_cb("spd frp", job, done)

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

    # ============ v8.2: REAL BROM/MTKClient operations ============

    def _mtk_cmd_or_stop(self, put):
        """MTKClient command lao; na mile to ERR return karo."""
        cmd = mtktool.find_mtk()
        if not cmd:
            put("❌ MTKClient nahi mila -- [TOOLS] Install MTKClient chalao.")
            return None
        return cmd

    def _pro_brom_connect(self):
        """[BROM] Connect -- VID:PID check ke saath REAL detection."""
        self._pro_set_status("BROM device dhoond rahe hain...", TEAL)

        def job(put):
            put("USB devices scan ho rahe hain (VID:PID)...")
            ok, detail = mtktool.detect_brom_vidpid()
            if ok:
                put(f"✅ BROM CONNECTED: {detail}")
                return "OK:BROM connected -- " + detail
            put("❌ " + detail)
            put("")
            put(mtktool.driver_hint_mtk())
            return "ERR:" + detail

        def done(res):
            if res.startswith("OK:"):
                self._pro_set_status("✅ " + res[3:], TEAL)
            else:
                self._pro_set_status("❌ " + res[4:], DANGER)
        self._run_bg_cb_live("brom connect", job, done)

    def _pro_spd_connect(self):
        """[SPD] Connect -- Unisoc BROM (1782:4D00) REAL detection."""
        self._pro_set_status("SPD device dhoond rahe hain...", TEAL)

        def job(put):
            put("USB devices scan ho rahe hain...")
            ok, detail = spdtool.detect_spd()
            if ok:
                put(f"✅ SPD CONNECTED: {detail}")
                return "OK:SPD connected -- " + detail
            put("❌ " + detail)
            put("Phone OFF karo, Vol UP+DOWN dabaye rakho + USB lagao.")
            put("Device Manager me 'SPRD U2S Diag' / 1782:4D00 aana chahiye.")
            return "ERR:" + detail

        def done(res):
            if res.startswith("OK:"):
                self._pro_set_status("✅ " + res[3:], TEAL)
            else:
                self._pro_set_status("❌ " + res[4:], DANGER)
        self._run_bg_cb_live("spd connect", job, done)

    def _pro_conn_check(self):
        """Sab modes ka device check: ADB, Fastboot, META, BROM, SPD."""
        self._pro_set_status("Sab modes check ho rahe hain...", TEAL)

        def job(put):
            put("--- DEVICE CHECK ---")
            # ADB
            try:
                if self.adb:
                    out = adbwrap.run(self.adb, ["devices"])
                    devs = [l for l in out.splitlines()[1:]
                            if l.strip() and "device" in l
                            and "unauthorized" not in l]
                    put(f"ADB: {'✅ ' + str(len(devs)) + ' device' if devs else '-- koi nahi'}")
                else:
                    put("ADB: -- (adb nahi mila)")
            except Exception as exc:
                put(f"ADB: error {exc}")
            # Fastboot
            try:
                if self.fb:
                    devs = features.fastboot_devices(self.fb)
                    put(f"Fastboot: {'✅ device mila' if devs else '-- koi nahi'}")
                else:
                    put("Fastboot: -- (fastboot nahi mila)")
            except Exception as exc:
                put(f"Fastboot: error {exc}")
            # META port
            ok, detail = mtktool.detect_meta_port()
            put(f"META: {'✅ ' + detail if ok else '-- ' + detail}")
            # BROM VID:PID
            ok, detail = mtktool.detect_brom_vidpid()
            put(f"BROM: {'✅ ' + detail if ok else '-- ' + detail}")
            # SPD
            ok, detail = spdtool.detect_spd()
            put(f"SPD: {'✅ ' + detail if ok else '-- ' + detail}")
            put("--- check mukammal ---")
            return "OK:device check mukammal (uper dekho)"

        def done(res):
            self._pro_set_status("✅ " + res[3:], TEAL)
        self._run_bg_cb_live("device check", job, done)

    def _pro_frp_brom(self):
        """[BROM] Erase FRP -- REAL via MTKClient."""
        if not self._confirm(
                "BROM FRP Erase (REAL)",
                "MTKClient se FRP partition ERASE hogi.\n\n"
                "1. Phone BILKUL OFF karo\n"
                "2. Vol UP dabaye rakho + USB lagao\n\n"
                "Sirf apne phone ya customer ki ijazat se karo.\n\n"
                "Jari rakho?"):
            return
        self._pro_set_status("FRP erase ho raha hai (MTKClient)...", TEAL)

        def job(put):
            cmd = self._mtk_cmd_or_stop(put)
            if not cmd:
                return "ERR:MTKClient nahi mila"
            put("PreLoader/BROM ka intezar (60s)...")
            ok, detail = mtktool.wait_preloader(60, put)
            if not ok:
                put("Tip: Vol DOWN se try karo, cable/port badlo.")
                return "ERR:" + detail
            put(f"Device: {detail}")
            da = self._da_loader()
            if da:
                put(f"DA use ho rahi hai: {da}")
            ok, msg = mtktool.run_mtk(cmd, ["e", "frp"], put, loader=da)
            if ok:
                return "OK:FRP erase ho gaya! Phone reboot karo."
            if "daa" in msg.lower() or "sla" in msg.lower() or "auth" in msg.lower():
                put("⚠️ Phone ne auth manga (DAA/SLA) -- is model par")
                put("   official DA file ya vendor tool darkar hai.")
            return "ERR:" + msg

        def done(res):
            if res.startswith("OK:"):
                self._pro_set_status("✅ " + res[3:], TEAL)
            else:
                self._pro_set_status("❌ " + res[4:], DANGER)
        self._run_bg_cb_live("brom frp erase", job, done)

    def _pro_wipe_brom(self):
        """[BROM] Factory Reset -- REAL via MTKClient."""
        if not self._confirm(
                "BROM Factory Reset (REAL)",
                "⚠️ Phone ka SARA DATA delete ho jayega!\n"
                "(metadata + userdata + md_udc erase honge)\n\n"
                "Sirf apne phone ya customer ki ijazat se karo.\n\n"
                "Jari rakho?"):
            return
        self._pro_set_status("Factory reset ho raha hai (MTKClient)...", TEAL)

        def job(put):
            cmd = self._mtk_cmd_or_stop(put)
            if not cmd:
                return "ERR:MTKClient nahi mila"
            put("PreLoader/BROM ka intezar (60s)...")
            ok, detail = mtktool.wait_preloader(60, put)
            if not ok:
                return "ERR:" + detail
            put(f"Device: {detail}")
            da = self._da_loader()
            if da:
                put(f"DA use ho rahi hai: {da}")
            ok, msg = mtktool.run_mtk(
                cmd, ["e", "metadata,userdata,md_udc"], put, loader=da)
            if ok:
                return "OK:Factory reset ho gaya! Pehle boot me 5-10 min lag sakte hain."
            return "ERR:" + msg

        def done(res):
            if res.startswith("OK:"):
                self._pro_set_status("✅ " + res[3:], TEAL)
            else:
                self._pro_set_status("❌ " + res[4:], DANGER)
        self._run_bg_cb_live("brom factory reset", job, done)

    def _pro_brom_reset(self):
        """BROM se phone reboot (mtk reset)."""
        self._pro_set_status("BROM se reboot...", TEAL)

        def job(put):
            cmd = self._mtk_cmd_or_stop(put)
            if not cmd:
                return "ERR:MTKClient nahi mila"
            put("PreLoader/BROM ka intezar (30s)...")
            ok, detail = mtktool.wait_preloader(30, put)
            if not ok:
                return "ERR:" + detail
            ok, msg = mtktool.run_mtk(cmd, ["reset"], put,
                                      loader=self._da_loader())
            return ("OK:reboot command bhej diya!" if ok else "ERR:" + msg)

        def done(res):
            self._pro_set_status(("✅ " if res.startswith("OK:") else "❌ ")
                                 + res[4:], TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb_live("brom reset", job, done)

    def _pro_part_gpt(self):
        """[BROM] Partition table parho (mtk printgpt) -- REAL."""
        self._pro_set_status("Partition table parh rahe hain...", TEAL)

        def job(put):
            cmd = self._mtk_cmd_or_stop(put)
            if not cmd:
                return "ERR:MTKClient nahi mila"
            put("PreLoader/BROM ka intezar (60s)...")
            ok, detail = mtktool.wait_preloader(60, put)
            if not ok:
                return "ERR:" + detail
            ok, msg = mtktool.run_mtk(cmd, ["printgpt"], put,
                                      loader=self._da_loader())
            return ("OK:partition table upar dekho" if ok else "ERR:" + msg)

        def done(res):
            self._pro_set_status(("✅ " if res.startswith("OK:") else "❌ ")
                                 + res[4:], TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb_live("printgpt", job, done)

    def _pro_part_read(self):
        """[BROM] Partition backup (mtk r) -- REAL."""
        part = simpledialog.askstring(
            "Partition Backup", "Kaunsi partition backup karni hai?\n"
            "(e.g. boot, nvram, frp, persist)", parent=self)
        if not part:
            return
        part = part.strip()
        if not part.replace("_", "").isalnum():
            self._pro_set_status("❌ Partition naam ghalat hai.", DANGER)
            return
        out = filedialog.asksaveasfilename(
            parent=self, title="Backup kahan save karo",
            defaultextension=".bin",
            initialfile=f"{part}_backup.bin",
            filetypes=[("Binary", "*.bin"), ("All", "*.*")])
        if not out:
            return
        self._pro_set_status(f"{part} backup ho raha hai...", TEAL)

        def job(put):
            cmd = self._mtk_cmd_or_stop(put)
            if not cmd:
                return "ERR:MTKClient nahi mila"
            put("PreLoader/BROM ka intezar (60s)...")
            ok, detail = mtktool.wait_preloader(60, put)
            if not ok:
                return "ERR:" + detail
            ok, msg = mtktool.run_mtk(cmd, ["r", part, out], put,
                                      loader=self._da_loader())
            return (f"OK:{part} backup ho gaya: {out}" if ok else "ERR:" + msg)

        def done(res):
            self._pro_set_status(("✅ " if res.startswith("OK:") else "❌ ")
                                 + res[4:], TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb_live("partition backup", job, done)

    def _pro_flash_part(self):
        """[BROM] Partition flash (mtk w) -- REAL."""
        img = filedialog.askopenfilename(
            parent=self, title="Image file select karo (.img/.bin)",
            filetypes=[("Images", "*.img *.bin"), ("All", "*.*")])
        if not img:
            return
        part = simpledialog.askstring(
            "Flash Partition", "Kaunsi partition par likhna hai?\n"
            "(e.g. boot, recovery, vbmeta)", parent=self)
        if not part:
            return
        part = part.strip()
        if not self._confirm(
                "Partition Flash (REAL)",
                f"File: {img}\nPartition: {part}\n\n"
                "⚠️ Ghalat file/partition = DEAD phone!\n"
                "Sirf apne MODEL ki sahi file use karo.\n\nJari rakho?"):
            return
        self._pro_set_status(f"{part} flash ho raha hai...", TEAL)

        def job(put):
            cmd = self._mtk_cmd_or_stop(put)
            if not cmd:
                return "ERR:MTKClient nahi mila"
            put("PreLoader/BROM ka intezar (60s)...")
            ok, detail = mtktool.wait_preloader(60, put)
            if not ok:
                return "ERR:" + detail
            ok, msg = mtktool.run_mtk(cmd, ["w", part, img], put,
                                      loader=self._da_loader())
            return (f"OK:{part} flash ho gaya!" if ok else "ERR:" + msg)

        def done(res):
            self._pro_set_status(("✅ " if res.startswith("OK:") else "❌ ")
                                 + res[4:], TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb_live("partition flash", job, done)

    def _pro_flash_fw(self):
        """[BROM] Firmware flash -- scatter validate + SP Flash Tool launch.

        MTKClient scatter files nahi leta; poori firmware SP Flash Tool
        (official, free) se flash hoti hai. Ye button: scatter validate
        karta hai, BROM detect karta hai, aur SP Flash Tool khol deta hai.
        """
        scat = filedialog.askopenfilename(
            parent=self, title="Scatter file select karo (MTxxxx_Android_scatter.txt)",
            filetypes=[("Scatter", "*scatter*.txt"), ("All", "*.*")])
        if not scat:
            return
        self._pro_set_status("Scatter check ho raha hai...", TEAL)

        def job(put):
            import re as _re
            try:
                with open(scat, "r", errors="replace") as f:
                    txt = f.read()
            except Exception as exc:
                return f"ERR:file nahi khuli: {exc}"
            parts = _re.findall(r"partition_name:\s*(\S+)", txt)
            put(f"Scatter OK: {len(parts)} partitions mili.")
            put("Pehli partitions: " + ", ".join(parts[:8]))
            # BROM detect (optional lekin madadgar)
            ok, detail = mtktool.detect_brom_vidpid()
            put(f"BROM: {'✅ ' + detail if ok else '-- ' + detail}")
            # SP Flash Tool dhoondo
            spft = self._find_spft()
            if spft:
                put(f"SP Flash Tool mila: {spft}")
                put("Khola ja raha hai -- scatter manually load karo.")
                try:
                    import subprocess as _sp
                    _sp.Popen([spft])
                    return ("OK:SP Flash Tool khol diya! Scatter load karke "
                            "Download dabao.")
                except Exception as exc:
                    put(f"Open fail: {exc}")
            put("")
            put("SP Flash Tool nahi mila. Steps:")
            put("1. SP Flash Tool download karo (official, free).")
            put("2. Scatter-loading -> ye file select karo.")
            put("3. Phone OFF + Vol key + USB, phir Download dabao.")
            put(f"Scatter: {scat}")
            return ("OK:scatter valid hai -- SP Flash Tool se flash karo "
                    "(guide upar)")

        def done(res):
            self._pro_set_status(("✅ " if res.startswith("OK:") else "❌ ")
                                 + res[4:], TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb_live("firmware flash", job, done)

    def _find_spft(self):
        """SP Flash Tool exe dhoondo (common paths)."""
        import glob as _g
        cands = []
        for base in (os.path.expandvars("%ProgramFiles%"),
                     os.path.expandvars("%ProgramFiles(x86)%"),
                     os.path.expandvars("%USERPROFILE%\\Desktop"),
                     os.path.expandvars("%USERPROFILE%\\Downloads")):
            cands += _g.glob(os.path.join(base, "**", "flash_tool.exe"),
                             recursive=True)
        return cands[0] if cands else None

    def _pro_mtk_install(self):
        """[TOOLS] MTKClient install (pip) -- REAL."""
        if not self._confirm(
                "MTKClient Install",
                "pip se MTKClient install hoga (internet darkar hai).\n"
                "1-2 minute lag sakte hain.\n\nJari rakho?"):
            return
        self._pro_set_status("MTKClient install ho raha hai...", TEAL)

        def job(put):
            ok = mtktool.install_mtkclient(put)
            if ok:
                cmd = mtktool.find_mtk()
                ver = mtktool.mtk_version(cmd) if cmd else "?"
                self.after(0, self._pro_refresh_ops)
                return f"OK:MTKClient v{ver} ready! BROM operations unlock ho gaye."
            return ("ERR:install fail -- manually: pip install mtkclient")

        def done(res):
            self._pro_set_status(("✅ " if res.startswith("OK:") else "❌ ")
                                 + res[4:], TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb_live("mtkclient install", job, done)

    def _pro_spd_install(self):
        """[TOOLS] spd_dump install guide."""
        self.log("=" * 50)
        self.log("[TOOLS] spd_dump install (Unisoc) -- steps:")
        self.log("1. GitHub kholo: github.com/bkerler/spreadtrum_flash")
        self.log("2. Repo download/zip karo, extract karo.")
        self.log("3. Folder ko C:\\spd_dump me rakho.")
        self.log("4. pip install pyusb")
        self.log("5. Zadig se 'SPRD U2S Diag' par WinUSB driver lagao.")
        self.log("Phir ye tool khud spd_dump dhoond lega (PATH ya tools/spd_dump).")
        self.log("=" * 50)
        if self._confirm("spd_dump",
                         "Install guide log me hai.\n\n"
                         "GitHub page kholun? (github.com/bkerler/spreadtrum_flash)"):
            webbrowser.open("https://github.com/bkerler/spreadtrum_flash")
        self._pro_set_status("spd_dump guide log me hai.", TEAL)

    def _pro_devmgr(self):
        """[TOOLS] Windows Device Manager kholo -- REAL."""
        try:
            import subprocess as _sp
            _sp.Popen("devmgmt.msc", shell=True)
            self._pro_set_status("✅ Device Manager khol diya.", TEAL)
            self.log("Device Manager khol diya -- COM ports / drivers check karo.")
        except Exception as exc:
            self._pro_set_status(f"❌ {exc}", DANGER)

    # ============ v8.2: DA Auto-Finder ============
    def _pro_da_finder(self):
        """🔍 DA Auto-Finder: chip -> database -> download -> auto-load."""
        m = self._pro_state.get("model") or {}
        chip_guess = datool.normalize_chip(m.get("chipset", ""))
        chip = simpledialog.askstring(
            "DA Auto-Finder", "Chip ka naam likho (e.g. MT6765):",
            initialvalue=chip_guess, parent=self)
        if not chip:
            return
        chip = datool.normalize_chip(chip)
        if not chip:
            self._pro_set_status("❌ Chip naam samajh nahi aaya.", DANGER)
            return
        self._pro_set_status(f"DA dhoond rahe hain: {chip}...", TEAL)

        def job(put):
            put(f"=== DA AUTO-FINDER: {chip} ===")
            cached = datool.cached_da(chip)
            if cached:
                put(f"✅ Cache me DA mili: {cached}")
                self._da_path = cached
                put("Ye DA ab BROM operations me auto-use hogi (--loader).")
                return f"OK:DA ready (cache): {cached}"
            put("Database fetch ho rahi hai...")
            db, src = datool.fetch_db()
            put(f"Database source: {src}")
            if not db:
                put("❌ Database nahi mili (internet check karo).")
                return "ERR:database nahi mili"
            key, entry = datool.find_entry(db, chip)
            if not entry:
                put(f"❌ '{chip}' database me nahi hai.")
                put("Day 1 par sab chips nahi honge -- database bharegi.")
                put("Hal: official firmware download karo, uske andar")
                put("DA file hoti hai (Download Agent field me select karo).")
                return "ERR:noentry:" + chip
            put(f"Entry mili: {key}")
            note = entry.get("note", "")
            if note:
                put("Note: " + note)
            url = (entry.get("da_url") or "").strip()
            if not url:
                fh = entry.get("firmware_hint", "")
                if fh:
                    put("Firmware hint: " + fh)
                put("")
                put("Is chip ka koi public download link nahi --")
                put("firmware wali DA use karo (SP Flash Tool me).")
                put("Cache folder khola ja raha hai (DA yahan rakho).")
                datool.open_cache_folder()
                return "ERR:nourl:" + chip
            put("Download ho raha hai...")
            last_pct = [0]

            def _prog(d, t):
                pct = d * 100 // t
                if pct - last_pct[0] >= 10:
                    last_pct[0] = pct
                    put(f"  ... {pct}%")

            ok, res = datool.download_da(url, f"{chip}.bin", _prog)
            if ok:
                self._da_path = res
                put(f"✅ DA download ho gayi: {res}")
                put("Ye DA ab BROM operations me auto-use hogi (--loader).")
                return f"OK:DA ready: {res}"
            put("❌ " + res)
            return "ERR:download fail"

        def done(res):
            if res.startswith("OK:"):
                self._pro_set_status("✅ " + res[3:], TEAL)
            elif res.startswith("ERR:noentry:") or res.startswith("ERR:nourl:"):
                self._pro_set_status(
                    "⚠️ DA nahi mili -- detail log me hai.", WARN_BG)
                self._ask_da_share(res.split(":", 2)[2])
            else:
                self._pro_set_status("❌ " + res[4:], DANGER)
        self._run_bg_cb_live("da finder", job, done)

    def _ask_da_share(self, chip):
        """'DA Share karo' dialog -- database grow karegi."""
        if not self._confirm(
                "DA Share karo?",
                f"'{chip}' ka DA database me nahi hai.\n\n"
                "Agar tumhare paas is chip ki WORKING DA file ka\n"
                "public link hai to share karo -- sab technicians\n"
                "ka faida hoga!\n\n"
                "Template banau?"):
            return
        dlg = tk.Toplevel(self)
        dlg.title(f"DA Share -- {chip}")
        dlg.configure(bg=BG)
        self._center(dlg)
        tk.Label(dlg, text="Neeche template me apna link bharo,\n"
                           "phir COPY karke Hamza ko bhejo:",
                 bg=BG, fg=FG, font=("Arial", 10), justify="left").pack(
                     padx=12, pady=8)
        txt = scrolledtext.ScrolledText(dlg, width=60, height=12, bg=PANEL,
                                        fg=FG, font=("Arial", 9))
        txt.pack(padx=12, pady=4)
        txt.insert("1.0", datool.share_template(chip))

        def _copy():
            dlg.clipboard_clear()
            dlg.clipboard_append(txt.get("1.0", "end").strip())
            self.log("DA template copy ho gaya -- Hamza ko bhejo!")
            dlg.destroy()
        tk.Button(dlg, text="📋 COPY", bg=TEAL, fg="#ffffff",
                  font=("Arial", 11, "bold"), padx=20, pady=6,
                  command=_copy).pack(pady=10)

    def _da_loader(self):
        """Active DA path (DA Finder se) ya None."""
        p = getattr(self, "_da_path", None)
        if p and os.path.isfile(p):
            return p
        return None

    # ============ v8.2: REAL SPD/Unisoc operations ============

    def _spd_cmd_or_stop(self, put):
        cmd = spdtool.find_spd_dump()
        if not cmd:
            put("❌ spd_dump nahi mila -- [TOOLS] Install spd_dump (guide) dekho.")
            return None
        return cmd

    def _spd_ask_fdl(self, put):
        """FDL files select karwao. Returns (fdl1, addr1, fdl2, addr2, exec_addr) ya None."""
        from tkinter import filedialog as _fd
        put("FDL files select karo (phone ke firmware/PAC se nikalti hain)...")
        fdl1 = _fd.askopenfilename(
            parent=self, title="fdl1 file select karo",
            filetypes=[("BIN", "*.bin"), ("All", "*.*")])
        if not fdl1:
            return None
        addr1 = simpledialog.askstring(
            "FDL1 Address", "fdl1 ka address likho:",
            initialvalue="0x5500", parent=self) or "0x5500"
        fdl2 = _fd.askopenfilename(
            parent=self, title="fdl2 file select karo",
            filetypes=[("BIN", "*.bin"), ("All", "*.*")])
        if not fdl2:
            return None
        addr2 = simpledialog.askstring(
            "FDL2 Address", "fdl2 ka address likho:",
            initialvalue="0x9efffe00", parent=self) or "0x9efffe00"
        m = (self._pro_state.get("model") or {})
        cpu = ""
        for key in spdtool.SPD_EXEC_ADDR:
            if key in (m.get("chipset", "").upper()):
                cpu = key
                break
        exec_addr = spdtool.SPD_EXEC_ADDR.get(
            cpu, spdtool.DEFAULT_EXEC_ADDR)
        ea = simpledialog.askstring(
            "exec_addr", f"exec_addr (SoC: {cpu or 'default'}):",
            initialvalue=exec_addr, parent=self) or exec_addr
        return fdl1, addr1.strip(), fdl2, addr2.strip(), ea.strip()

    def _pro_spd_frp(self):
        """[SPD] Erase FRP -- REAL via spd_dump (FDL darkar)."""
        if not self._confirm(
                "SPD FRP Erase (REAL)",
                "spd_dump se 'frp' partition ERASE hogi.\n\n"
                "Is ke liye FDL files (fdl1/fdl2) chahiye --\n"
                "jo phone ke FIRMWARE se nikalti hain.\n\n"
                "Sirf apne phone ya customer ki ijazat se karo.\n\n"
                "Jari rakho?"):
            return
        self._pro_set_status("SPD FRP erase ho raha hai...", TEAL)

        def job(put):
            cmd = self._spd_cmd_or_stop(put)
            if not cmd:
                return "ERR:spd_dump nahi mila"
            fdl = self._spd_ask_fdl(put)
            if not fdl:
                return "ERR:FDL select nahi hui"
            fdl1, addr1, fdl2, addr2, ea = fdl
            put("SPD BROM ka intezar (60s) -- phone OFF + Vol UP+DOWN + USB")
            ok, detail = spdtool.wait_spd(60, put)
            if not ok:
                return "ERR:" + detail
            put(f"Device: {detail}")
            args = spdtool.build_fdl_args(fdl1, addr1, fdl2, addr2, ea)
            args += ["erase_part", "frp", "reset"]
            ok, msg = spdtool.run_spd(cmd, args, put)
            return ("OK:FRP erase ho gaya! Phone reboot hoga." if ok
                    else "ERR:" + msg)

        def done(res):
            self._pro_set_status(("✅ " if res.startswith("OK:") else "❌ ")
                                 + res[4:], TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb_live("spd frp erase", job, done)

    def _pro_spd_wipe(self):
        """[SPD] Factory Reset -- REAL via spd_dump (FDL darkar)."""
        if not self._confirm(
                "SPD Factory Reset (REAL)",
                "⚠️ userdata erase hoga -- SARA DATA jayega!\n\n"
                "FDL files (fdl1/fdl2) darkar hain (firmware se).\n\n"
                "Sirf apne phone ya customer ki ijazat se karo.\n\n"
                "Jari rakho?"):
            return
        self._pro_set_status("SPD factory reset ho raha hai...", TEAL)

        def job(put):
            cmd = self._spd_cmd_or_stop(put)
            if not cmd:
                return "ERR:spd_dump nahi mila"
            fdl = self._spd_ask_fdl(put)
            if not fdl:
                return "ERR:FDL select nahi hui"
            fdl1, addr1, fdl2, addr2, ea = fdl
            put("SPD BROM ka intezar (60s)...")
            ok, detail = spdtool.wait_spd(60, put)
            if not ok:
                return "ERR:" + detail
            args = spdtool.build_fdl_args(fdl1, addr1, fdl2, addr2, ea)
            args += ["erase_part", "userdata", "reset"]
            ok, msg = spdtool.run_spd(cmd, args, put)
            return ("OK:Factory reset ho gaya!" if ok else "ERR:" + msg)

        def done(res):
            self._pro_set_status(("✅ " if res.startswith("OK:") else "❌ ")
                                 + res[4:], TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb_live("spd factory reset", job, done)

    def _pro_spd_flash_pac(self):
        """[SPD] PAC flash -- guide + tool launch (honest)."""
        self.log("=" * 50)
        self.log(spdtool.SPD_PAC_GUIDE)
        self.log("=" * 50)
        tool = self._find_spd_tool()
        if tool:
            self.log(f"Tool mila: {tool} -- khola ja raha hai.")
            try:
                import subprocess as _sp
                _sp.Popen([tool])
                self._pro_set_status("✅ SPD tool khol diya.", TEAL)
                return
            except Exception as exc:
                self.log(f"Open fail: {exc}")
        if self._confirm("SPD PAC Flash",
                         "PAC flashing SPD Upgrade Tool / ResearchDownload\n"
                         "se hoti hai (official, free).\n\n"
                         "Guide log me hai. Download page kholun?"):
            webbrowser.open(
                "https://www.google.com/search?q=SPD+Upgrade+Tool+latest+download")
        self._pro_set_status("PAC guide log me hai.", TEAL)

    def _find_spd_tool(self):
        import glob as _g
        pats = ["ResearchDownload.exe", "UpgradeDownload.exe",
                "SPD_Upgrade_Tool*.exe"]
        for base in (os.path.expandvars("%ProgramFiles%"),
                     os.path.expandvars("%ProgramFiles(x86)%"),
                     os.path.expandvars("%USERPROFILE%\\Desktop"),
                     os.path.expandvars("%USERPROFILE%\\Downloads")):
            for p in pats:
                hits = _g.glob(os.path.join(base, "**", p), recursive=True)
                if hits:
                    return hits[0]
        return None

    def _pro_spd_diag(self):
        """[SPD] Diag mode -- guide (honest)."""
        self.log("=" * 50)
        self.log(spdtool.SPD_DIAG_GUIDE)
        self.log("=" * 50)
        self._pro_set_status("Diag guide log me hai.", TEAL)
        messagebox.showinfo("SPD Diag Mode",
                            "Phone ON karo, dialer me likho:\n\n"
                            "*#*#83781#*#*\n\n"
                            "Engineering Mode -> Diag ON karo.\n"
                            "Detail guide log me hai.", parent=self)

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
        # REAL: META serial port par AT+EGMR bhejo (pyserial).
        self._pro_set_status(
            f"✅ IMEI valid: {clean}. META port dhoond rahe hain...", TEAL)

        def job(put):
            put("META COM port ka intezar (30s)...")
            put("Phone META mode me hona chahiye (adb reboot meta).")
            ok, detail = mtktool.wait_meta_port(30, put)
            if not ok:
                put("Tip: [REBOOT] -> Reboot to META Mode dabao, phir dobara.")
                return "ERR:" + detail
            m = __import__("re").search(r"(COM\d+)", detail, __import__("re").I)
            port = m.group(1) if m else None
            if not port:
                return "ERR:port naam nahi samajh aaya: " + detail
            put(f"Port: {port}")
            ok, msg = mtktool.imei_write_meta(port, clean, put)
            if ok:
                put("")
                put("Reboot karke *#06# se verify karo.")
                return f"OK:IMEI restore ho gaya ({clean})!"
            return "ERR:" + msg

        def done(res):
            if res.startswith("OK:"):
                self._pro_set_status("✅ " + res[3:], TEAL)
            else:
                self._pro_set_status("❌ " + res[4:], DANGER)
        self._run_bg_cb_live("meta imei restore", job, done)

    def _pro_meta_boot(self):
        """[REBOOT] Boot to META Mode -- REAL (adb reboot meta + verify)."""
        if not self.adb:
            self._pro_set_status("❌ adb nahi mila.", DANGER)
            return
        self._pro_set_status("META mode me bheja ja raha hai...", TEAL)

        def job(put):
            try:
                out = adbwrap.run(self.adb, ["reboot", "meta"])
                if out.strip():
                    put(out.strip()[:200])
            except Exception as exc:
                return f"ERR:adb reboot fail: {exc}"
            put("Phone reboot ho raha hai, META port ka intezar (40s)...")
            ok, detail = mtktool.wait_meta_port(40, put)
            if ok:
                return "OK:META mode active -- " + detail
            return ("ERR:META port nahi aaya -- phone manually META me le jao "
                    "(recovery se ya key combo)")

        def done(res):
            self._pro_set_status(("✅ " if res.startswith("OK:") else "❌ ")
                                 + res[4:], TEAL if res.startswith("OK:") else DANGER)
        self._run_bg_cb_live("boot meta", job, done)

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
            except (ValueError, Exception):
                pass  # pehle se mojood hai ya race condition
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
        # v8.4: First-run diagnostics — user ko foran pata chale kya kami hai
        self.after(500, self._pro_startup_diagnostics)

    def _pro_startup_diagnostics(self):
        """Startup par ADB/driver/phone check — masla ho to foran batayo."""
        issues = []
        if not self.adb:
            issues.append("❌ ADB nahi mila (platform-tools missing)")
        if not self.fb:
            issues.append("❌ Fastboot nahi mila (platform-tools missing)")

        # Phone check (sirf agar adb hai)
        phone_found = False
        if self.adb:
            try:
                out = adbwrap.run(self.adb, ["devices"])
                lines = [l for l in out.splitlines()[1:] if l.strip()]
                devs = [l for l in lines if "\tdevice" in l]
                unauth = [l for l in lines if "unauthorized" in l]
                if devs:
                    phone_found = True
                elif unauth:
                    issues.append("⚠️ Phone mila lekin 'unauthorized' — phone par Allow dabao")
            except Exception:
                pass

        if not phone_found and self.adb:
            issues.append("📱 Koi phone connect nahi (USB debugging ON karo)")

        if issues:
            msg = "🔧 STARTUP CHECK:\n\n" + "\n".join(issues) + "\n\n"
            if not self.adb or not self.fb:
                msg += "HAL: [TOOLS] → Install Drivers dabao,\nya platform-tools folder tool ke saath rakho."
            else:
                msg += "Phone lagao aur USB debugging ON karo."
            # Sirf pehli baar ya jab masla ho tab dikhao (status me hamesha)
            self._pro_set_status("⚠️ " + " | ".join(issues[:2]), DANGER)
            self.log("DIAGNOSTICS:\n" + "\n".join(issues))
        else:
            self._pro_set_status("✅ Sab ready: ADB + Phone connect!", TEAL)

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

    def _run_bg_live(self, label, job):
        """Background job with LIVE streaming log lines.

        job(put) -> final result string starting with 'OK:' ya 'ERR:'.
        put(line) log me foran line dalta hai (MTKClient jese lambi
        operations ke liye).
        """
        def worker():
            self._jobs.put(f">> {label}")
            try:
                res = job(lambda line: self._jobs.put(str(line)[:220]))
            except Exception as exc:  # noqa: BLE001 - show in log
                res = "ERR:" + str(exc)
            if res:
                self._jobs.put(str(res).strip()[:3000])
            self._jobs.put("done.")
        threading.Thread(target=worker, daemon=True).start()

    def _run_bg_cb_live(self, label, job, done):
        """_run_bg_live + completion callback (status line update)."""
        def worker():
            self._jobs.put(f">> {label}")
            try:
                res = job(lambda line: self._jobs.put(str(line)[:220]))
            except Exception as exc:  # noqa: BLE001 - show in log
                res = "ERR:" + str(exc)
            if res:
                self._jobs.put(str(res).strip()[:3000])
            self._jobs.put("done.")
            try:
                self.after(0, lambda: done(res or "ERR:khali jawab"))
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _run_bg_cb(self, label, job, done):
        """Background job + completion callback (v8.6: missing method fix)."""
        def worker():
            self._jobs.put(f">> {label}")
            try:
                res = job()
            except Exception as exc:  # noqa: BLE001
                res = "ERR:" + str(exc)
            if res:
                self._jobs.put(str(res).strip()[:3000])
            self._jobs.put("done.")
            try:
                self.after(0, lambda: done(res or "ERR:khali jawab"))
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _thread(self, job, done):
        """Simple background thread with callback (v8.6: missing method fix)."""
        self._run_bg_cb("task", job, done)

    def _need_mtk(self, put):
        """MTKClient check karo; na mile to seedhi guidance do."""
        cmd = mtktool.find_mtk()
        if cmd:
            ver = mtktool.mtk_version(cmd)
            put(f"MTKClient mil gaya (v{ver})")
            return cmd
        put("MTKClient nahi mila!")
        put("[TOOLS] -> [TOOLS] Install MTKClient dabao, phir dobara try karo.")
        put("Ya manually: pip install mtkclient")
        return None

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
    # v8.8: Single-instance lock - ek se zyada copy na khule
    import socket as _sock
    _lock_sock = None
    try:
        _lock_sock = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
        _lock_sock.bind(("127.0.0.1", 47891))
        _lock_sock.listen(1)
    except OSError:
        import tkinter.messagebox as _mb
        try:
            _root = __import__("tkinter").Tk()
            _root.withdraw()
            _mb.showwarning("Hamza GSM Tool",
                "Tool pehle se chal raha hai!\nTask Manager me purani copy band karo.")
            _root.destroy()
        except Exception:
            pass
        raise SystemExit(0)
    _stage("stage 7: starting ToolApp")
    _app = ToolApp()
    _stage("stage 8: entering mainloop")
    _app.mainloop()
