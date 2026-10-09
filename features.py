"""Servicing features. Parsers are pure functions (unit-tested);
actions take an adb/fastboot binary path and shell out through adbwrap.
"""

import platform
import re
import subprocess

from adbwrap import run

# Keywords used to *suggest* candidates when scanning for MDM-like apps.
# The user always picks from the list -- nothing is removed automatically.
MDM_KEYWORDS = (
    "mdm",
    "manageengine",
    "maas360",
    "airwatch",
    "intune",
    "companyportal",
    "workspaceone",
    "mobileiron",
    "soti",
    "42gears",
    "suremdm",
    "itadmin",
    "deviceadmin",
)

REBOOT_TARGETS = ("system", "recovery", "bootloader", "edl", "sideload", "meta")
# NOTE: "meta" = MediaTek META mode (adb reboot meta). Phone META mode me
# jata hai jahan vendor META tools (jaise Modem META) IMEI/NVRAM kaam karte hain.


# ------------------------------- parsers -------------------------------

def parse_adb_devices(text):
    """Parse `adb devices -l` -> [(serial, state), ...]."""
    devs = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("List of"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            devs.append((parts[0], parts[1]))
    return devs


def parse_fastboot_devices(text):
    """Parse `fastboot devices` -> [serial, ...]."""
    return [l.split()[0] for l in text.splitlines() if l.strip()]


def parse_packages(text):
    """Parse `pm list packages` -> [package.name, ...]."""
    pkgs = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            pkgs.append(line[len("package:"):])
    return pkgs


def find_suspicious_packages(packages, keywords=MDM_KEYWORDS):
    """Return packages whose name contains any keyword (case-insensitive)."""
    out = []
    for pkg in packages:
        low = pkg.lower()
        if any(k in low for k in keywords):
            out.append(pkg)
    return out


# Keywords for Transsion (Tecno/Infinix/Itel) ID / account-lock apps.
# Shown as candidates only -- the user always picks what to disable.
TRANSSION_ID_KEYWORDS = ("transsion",)


def find_transsion_id_packages(packages, keywords=TRANSSION_ID_KEYWORDS):
    """Return packages whose name contains any keyword (case-insensitive)."""
    out = []
    for pkg in packages:
        low = pkg.lower()
        if any(k in low for k in keywords):
            out.append(pkg)
    return out


def parse_device_admins(dumpsys_text):
    """Extract active device-admin components from `dumpsys device_policy`."""
    admins = []
    capture = False
    for line in dumpsys_text.splitlines():
        if "Active admin" in line:
            capture = True
        if capture:
            m = re.search(r"ComponentInfo\{([^}]+)\}", line)
            if m and m.group(1) not in admins:
                admins.append(m.group(1))
        if capture and line.strip().startswith("Active password"):
            capture = False
    return admins


# ------------------------------- actions -------------------------------

def _adb(adb, *args, serial=None, timeout=60):
    cmd = []
    if serial:
        cmd += ["-s", serial]
    return run(adb, cmd + list(args), timeout=timeout)


def adb_devices(adb):
    return parse_adb_devices(run(adb, ["devices", "-l"]))


def device_info(adb, serial=None):
    props = {
        "Model": "ro.product.model",
        "Brand": "ro.product.brand",
        "Android": "ro.build.version.release",
        "Security patch": "ro.build.version.security_patch",
        "CPU": "ro.product.cpu.abi",
        "Baseband": "gsm.version.baseband",
        "Serial": "ro.serialno",
    }
    info = {}
    for label, prop in props.items():
        try:
            info[label] = _adb(adb, "shell", "getprop", prop,
                               serial=serial).strip()
        except Exception as exc:  # noqa: BLE001 - report per-field
            info[label] = f"<error: {exc}>"
    return info


def reboot_device(adb, target="system", serial=None):
    if target not in REBOOT_TARGETS:
        raise ValueError(f"target must be one of {REBOOT_TARGETS}")
    if target == "system":
        return _adb(adb, "reboot", serial=serial)
    if target == "edl":
        return _adb(adb, "reboot", "edl", serial=serial)
    return _adb(adb, "reboot", target, serial=serial)


def list_packages(adb, serial=None):
    return parse_packages(_adb(adb, "shell", "pm", "list", "packages",
                                serial=serial, timeout=120))


def device_admins(adb, serial=None):
    return parse_device_admins(
        _adb(adb, "shell", "dumpsys", "device_policy",
             serial=serial, timeout=60))


def disable_package(adb, pkg, serial=None):
    """Disable an app for the main user (reversible with `pm enable`)."""
    return _adb(adb, "shell", "pm", "disable-user", "--user", "0", pkg,
                serial=serial)


def enable_package(adb, pkg, serial=None):
    return _adb(adb, "shell", "pm", "enable", pkg, serial=serial)


def uninstall_package(adb, pkg, serial=None):
    """Uninstall for user 0, keeping data (reversible via factory reset)."""
    return _adb(adb, "shell", "pm", "uninstall", "-k", "--user", "0", pkg,
                serial=serial)


def install_apk(adb, apk_path, serial=None):
    return _adb(adb, "install", "-r", apk_path, serial=serial, timeout=180)


def remove_device_admin(adb, component, serial=None):
    """Remove a device admin (works only if the admin allows it)."""
    return _adb(adb, "shell", "dpm", "remove-active-admin", component,
                serial=serial)


# ------------------------------ fastboot -------------------------------

def _fb(fb, *args, serial=None, timeout=60):
    cmd = []
    if serial:
        cmd += ["-s", serial]
    return run(fb, cmd + list(args), timeout=timeout)


def fastboot_devices(fb):
    return parse_fastboot_devices(run(fb, ["devices"]))


def fastboot_getvar_all(fb, serial=None):
    return _fb(fb, "getvar", "all", serial=serial, timeout=60)


def fastboot_unlock(fb, serial=None):
    return _fb(fb, "flashing", "unlock", serial=serial)


def fastboot_lock(fb, serial=None):
    return _fb(fb, "flashing", "lock", serial=serial)


def fastboot_flash(fb, partition, image, serial=None):
    return _fb(fb, "flash", partition, image, serial=serial, timeout=600)


def fastboot_erase(fb, partition, serial=None):
    """Fastboot partition erase (masalan 'frp', 'config')."""
    return _fb(fb, "erase", partition, serial=serial, timeout=120)


def fastboot_reboot(fb, serial=None):
    return _fb(fb, "reboot", serial=serial)


# --------------------------- IMEI (original only) ---------------------------
# SAKHT RULE: sirf phone ka ORIGINAL IMEI (box/sticker wala) restore hota hai.
# Koi random/new IMEI generate karne wala function yahan NAHI hai aur kabhi
# add NAHI hoga -- IMEI tampering PTA ke under illegal hai.

def validate_imei(imei):
    """Validate a 15-digit IMEI: format + Luhn checksum.

    Returns (True, clean_imei) or (False, reason). Pure function.
    """
    if imei is None:
        return False, "khali hai"
    s = re.sub(r"[\s\-]", "", str(imei))
    if not s.isdigit():
        return False, "sirf 0-9 digits hone chahiye"
    if len(s) != 15:
        return False, f"15 digits hone chahiye (mile {len(s)})"
    total = 0
    for i, ch in enumerate(s):
        d = int(ch)
        if i % 2 == 1:  # 15-digit IMEI: odd indices double hote hain
            d *= 2
            if d > 9:
                d -= 9
        total += d
    if total % 10 != 0:
        return False, "checksum ghalat hai -- number dobara check karo"
    return True, s


def imei_at_commands(imei):
    """MTK META mode ke AT commands (reference ke liye).

    Ye commands Modem META / Maui META jese vendor tool me chalte hain.
    AT+EGMR=1,7,"..."  -> SIM slot 1 ka IMEI likhta hai
    AT+EGMR=1,10,"..." -> SIM slot 2 ka IMEI likhta hai
    """
    return (f'AT+EGMR=1,7,"{imei}"',
            f'AT+EGMR=1,10,"{imei}"')


# --------------------------- BROM / PreLoader ---------------------------

def detect_mtk_preloader():
    """Windows par MediaTek PreLoader/BROM USB device detect karo.

    Returns (True, detail) ya (False, reason). Sirf detection hai --
    asal flashing vendor tools (SP Flash Tool / MTKClient) se hoti hai.
    """
    if platform.system() != "Windows":
        return False, "device detection sirf Windows par supported hai"
    try:
        out = subprocess.run(
            ["wmic", "path", "Win32_PnPEntity", "get", "Name"],
            capture_output=True, text=True, timeout=25).stdout or ""
    except Exception as exc:  # noqa: BLE001 - user ko reason dikhao
        return False, f"wmic error: {exc}"
    hits = []
    for line in out.splitlines():
        low = line.lower()
        if ("mediatek" in low and
                ("preloader" in low or "vcom" in low or "usb port" in low)):
            hits.append(line.strip())
        elif "mtk usb port" in low:
            hits.append(line.strip())
    if hits:
        return True, "; ".join(hits[:3])
    return False, "koi MTK PreLoader/BROM device nahi mila"


BROM_FRP_GUIDE = """[BROM] FRP ERASE (MTK) -- step-by-step:

1. Phone BILKUL OFF karo (10 sec power dabaye rakho).
2. Volume UP dabaye rakho + USB cable lagao.
   (Kuch models me Vol DOWN; port ka naam check karo.)
3. Device Manager me "MediaTek PreLoader USB VCOM" aana chahiye.
   PreLoader sirf chand second rehta hai -- jaldi karo!

ASAL ERASE (2 free tareeqe -- dono aazmaye hue):

  A) MTKClient (github.com/bkerler/mtkclient):
       python mtk.py e frp
     (Pehle: pip install -r requirements.txt)

  B) SP Flash Tool:
     - "Format" tab kholo -> "Manual Format Flash"
     - FRP partition ka address scatter file se lo
     - Start dabao

SAFETY:
- Sirf apne phone ya customer ki ijazat se karo.
- Pehle NVRAM/IMEI ka backup lo (Backup tab) -- BROM me ghalti
  se IMEI null ho sakta hai!
- DA (Download Agent) error aaye to test-point wala rasta use karo
  (Test Point tab -> exact model verify karo).
"""
