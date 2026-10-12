"""Free external tools launcher for Hamza GSM Tool v8.3.

Har tool: official download link + local launch.
Tools ~/workspace/gsmtool/freetools/<key>/ me extract karo, phir tool se khul jayega.
"""

import os

TOOLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "freetools")

# key: (display name, description_urdu, download_url, exe_names_to_find)
FREE_TOOLS = {
    "samfw": (
        "SamFw FRP Tool",
        "Samsung FRP remove (free). Android 9-15. Setup wizard → *#0*# → Remove FRP.",
        "https://samfw.com",
        ["SamFwTool.exe", "SamFwFRPTool.exe"],
    ),
    "odin": (
        "Odin3 v3.14.4",
        "Samsung firmware flashing (BL/AP/CP/CSC). Sirf genuine v3.14.4 use karo.",
        "https://odindownload.com",
        ["Odin3.exe", "Odin3 v3.14.4.exe"],
    ),
    "3utools": (
        "3uTools",
        "iPhone flashing, backup, battery info, exit recovery. 100% free.",
        "https://www.3u.com",
        ["3uTools.exe"],
    ),
    "scrcpy": (
        "scrcpy",
        "Phone screen PC par mirror + control. Tooti screen ka data nikalo.",
        "https://github.com/Genymobile/scrcpy/releases",
        ["scrcpy.exe"],
    ),
    "miflash": (
        "MiFlash",
        "Xiaomi fastboot ROM flashing. 'clean all' select karo (lock wala nahi!).",
        "https://xiaomiflash.com",
        ["XiaoMiFlash.exe", "MiFlash.exe"],
    ),
    "frija": (
        "Frija",
        "Samsung firmware Samsung ke server se direct download (fast, free).",
        "https://forum.xda-developers.com/t/tool-frija-samsung-firmware-downloader-checker.3910594/",
        ["Frija.exe"],
    ),
    "realmeflash": (
        "Realme Flash Tool",
        "Realme/Oppo OFP firmware flashing. Unlocked bootloader chahiye.",
        "https://www.thecustomdroid.com/realme-flash-tool/",
        ["RealmeFlash.exe"],
    ),
    "qpst": (
        "QPST / QFIL",
        "Qualcomm EDL (9008) flashing. QDLoader drivers ke saath.",
        "https://qpsttool.com",
        ["QFIL.exe"],
    ),
    "androidwintool": (
        "Android Win Tool",
        "FREE: Infinix/Tecno/Itel Anti-Crack Remove! MTK devices. Register (free) → Anti-Crack Remove.",
        "https://github.com/Android-Win-Tools-Update",
        ["AndroidWinTool.exe", "Android Win Tool.exe"],
    ),
    "aftersaletool": (
        "AfterSaleTool V7.2025.01.07 (Transsion)",
        "FREE: Tecno/Infinix/Itel IMEI/SN/WiFi/BT repair! MTK phones. No root, no login. Sirf ORIGINAL IMEI likho (dabba/sticker se).",
        "https://www.officialroms.com/after-sales-tool/",
        ["AfterSalesFull.exe", "AfterSaleTool.exe"],
    ),
    "mtkclient_gui": (
        "MTKClient GUI",
        "FREE: MTK BROM operations — FRP, format, backup. Python based.",
        "https://github.com/bkerler/mtkclient",
        ["mtk_gui.exe", "mtk_gui"],
    ),
    "spflashtool": (
        "SP Flash Tool",
        "FREE: Official MTK firmware flashing tool. Scatter file se flash.",
        "https://spflashtool.com",
        ["flash_tool.exe"],
    ),
    "egsmtool": (
        "E-GSM Tool (1-MONTH FREE TRIAL)",
        "All brands: FRP, flash, IMEI, Mi Account. Sirf 1 mahina free trial, phir paid.",
        "https://egsmtool.com",
        ["EGSMTool.exe", "E-GSM Tool.exe"],
    ),
    # ---- v8.4: mazeed free tools (research se) ----
    "mtkclient": (
        "mtkclient (GitHub)",
        "FREE open-source: MTK BROM exploit, FRP erase, flash read/write. Python + UsbDk.",
        "https://github.com/bkerler/mtkclient",
        ["mtk_gui.exe", "mtk_gui", "mtk.exe"],
    ),
    "spflashtool_official": (
        "SP Flash Tool (Official)",
        "Official MediaTek flasher — scatter firmware flashing. 100% free.",
        "https://spflashtool.com",
        ["flash_tool.exe"],
    ),
    "sfdtool": (
        "SFD Tool GUI (SPD FREE)",
        "Open-source Unisoc tool: PAC flash, partition manager, slot A/B. No credits!",
        "https://github.com",
        ["SFDTool.exe", "sfdtool.exe"],
    ),
    "spdresearch": (
        "SPD Research Tool (Official)",
        "Official Unisoc flasher (PAC firmware). Portable, free.",
        "http://spdflashtool.com",
        ["ResearchDownload.exe"],
    ),
    "edl_qc": (
        "edl (Qualcomm Open-Source)",
        "FREE QC Firehose/Sahara CLI — QFIL jaisa, open-source. Python.",
        "https://github.com/lwz114/edl",
        ["edl.exe", "edl"],
    ),
    "miunlock": (
        "Mi Unlock (Official Xiaomi)",
        "Official bootloader unlock — free (7 din wait). xiaomi.com se.",
        "https://www.mi.com/global/unlock/",
        ["MiUnlock.exe", "miflash_unlock.exe"],
    ),
    "modemmeta": (
        "ModemMeta (MTK IMEI Restore)",
        "MTK META mode: DABBE wala ORIGINAL IMEI likho (000000 fix). Free.",
        "https://www.getdroidtips.com",
        ["ModemMeta.exe"],
    ),
    "snwriter": (
        "SN Writer (MTK Official)",
        "MTK official: serial/IMEI writer. Original restore ke liye.",
        "https://spflashtool.com",
        ["SN Writer.exe", "SNWriter.exe"],
    ),
    "gstsamunlock": (
        "G-ST SamUnlock V7.8 [Community]",
        "Samsung all-chipset FRP/flash/serial. Free (community tool — scan karo).",
        "https://www.advancedsetting.com",
        ["G-ST SamUnlock.exe", "SamUnlock.exe"],
    ),
    "primetoolx": (
        "Prime Tool X [Community]",
        "Samsung/Xiaomi/Motorola FRP (Android 12-16). Free, no login (scan karo).",
        "https://gsmxblog.com",
        ["PrimeToolX.exe"],
    ),
    "bmbtool": (
        "BMB Tool Pro [Community]",
        "Samsung/Xiaomi/Vivo/Oppo/Tecno FRP (MTK+QC). Free (scan karo).",
        "https://www.youtube.com",
        ["BMBTool.exe"],
    ),
    "miketunlocker": (
        "Mike Techs Unlocker Pro [Community]",
        "35+ brands: FRP, screen lock, flash, EDL/SPD. Free ~750MB (scan karo).",
        "https://www.sergesmiketechs.com",
        ["MikeTechsUnlocker.exe"],
    ),
    "oplus_edl": (
        "OPLUS EDL Tool [Community]",
        "Realme/OnePlus/Oppo EDL flashing. Free (scan karo).",
        "https://www.fixbynaem.com",
        ["OPLUS_EDL.exe", "OplusEDL.exe"],
    ),
    # ---- v8.5: Transsion online server + ID remove ----
    "carlcare_otp": (
        "Carlcare OTP Loader (Transsion Server)",
        "ONLINE SERVER: Tecno/Infinix/Itel official aftersales auth! IMEI write bina anti-crack trigger. FREE open-source.",
        "https://github.com/cainal56/carlcare-otp-loader-or-transsion-aftersales-auth",
        ["CarlcareOTP.exe", "OTP_Loader.exe", "carlcare_otp.exe"],
    ),
    "transsion_mdm": (
        "Tecno/Infinix MDM Remove Tool",
        "FREE one-click: MDM lock remove + QR ADB enabler. Windows 7-11.",
        "https://www.mobilerdx.com/tecno-infinix-mdm-remove-tool/",
        ["MDMtool.exe", "MDM_Tool.exe"],
    ),
    "oumse_spd": (
        "OumseGsmToolPro (SPD Transsion)",
        "SPD/Unisoc: bootloader unlock, anti-crack, MDM/SecurityPlugin remove, ROM maker.",
        "https://oumsegsm.com/download",
        ["OumseGsmToolPro.exe"],
    ),
    "multiunlockmdm": (
        "MultiUnlockMDM (Transsion ID)",
        "Tecno/Infinix/Itel ID bypass — Android 14/15/16. Video guide ke saath.",
        "https://www.youtube.com/watch?v=67-kFzLGFNw",
        ["MultiUnlockMDM.exe"],
    ),
    # ---- v8.6: Latest Samsung FRP tools ----
    "halabtech_frp": (
        "HalabTech FRP Tool (Samsung Latest)",
        "One-click Samsung FRP via MTP — Android 15/16, sab chipsets. FREE, no login!",
        "https://mobileteamofficials.com",
        ["HalabTechFRP.exe", "HalabTech FRP.exe"],
    ),
    "halabtech_v4": (
        "HalabTech Tool V4.0 (Samsung Full)",
        "Samsung servicing: Flash/FRP/IMEI/ADB. Free login.",
        "https://gsmfixtech360.com",
        ["HalabTech.exe", "HalabTechTool.exe"],
    ),
    "samfw_v6": (
        "SamFw Tool V6.0.1 (Latest)",
        "Latest SamFw — Samsung FRP + flash. Basic free, kuch features paid.",
        "https://samfw.com",
        ["SamFwTool.exe", "SamFwFRPTool.exe"],
    ),
    "imeistar_frp": (
        "Samsung FRP Tool (imeistar)",
        "One-click MTP FRP — Android 13-16. Lightweight, free, no credits.",
        "https://www.advancedsetting.com",
        ["SamsungFRP.exe", "imeistarFRP.exe"],
    ),
    # ---- v8.7: Transsion FRP latest ----
    "phoenix_tool": (
        "Phoenix Service Tool (Transsion FRP FREE!)",
        "⭐ Infinix/Tecno/Itel FRP + Flashing BILKUL FREE! Android 13-16, MTK+SPD. Free register.",
        "https://phoenixservicetool.com",
        ["PhoenixServiceTool.exe", "Phoenix.exe"],
    ),
    "samfirm_aio": (
        "SamFirm A.I.O v1.4.3 (FRP)",
        "1-click FRP, portable ~122MB. Password: RSL Mobile Solution YouTube.",
        "https://rslmobilesolution.blogspot.com",
        ["SamFirmAIO.exe", "SamFirm.exe"],
    ),
    "oplusprologin": (
        "OPlusProLogin V6 (Transsion)",
        "FRP + Auth OTP login — MTK & SPD Transsion. Free.",
        "https://allunlocker.com",
        ["OPlusProLogin.exe"],
    ),
    "mtk_cli": (
        "MTK CLI Tool V1.0 (FRP)",
        "Simple menu: 1-Format, 2-FRP. MTK BROM. Free.",
        "https://bypassfrpfiles.com",
        ["MTKCLI.exe", "MTK_CLI.exe"],
    ),
    "spd_frp_simple": (
        "Simple SPD FRP Tool",
        "SPD fastboot FRP — '2' dabao. Free.",
        "https://bypassfrpfiles.com",
        ["SPDFRP.exe", "SimpleSPDFRP.exe"],
    ),
}


def find_tool_exe(key):
    """Tool ka exe dhoondo. (path ya None)"""
    info = FREE_TOOLS.get(key)
    if not info:
        return None
    folder = os.path.join(TOOLS_DIR, key)
    for exe in info[3]:
        p = os.path.join(folder, exe)
        if os.path.isfile(p):
            return p
        # subfolder me bhi dhoondo (1 level)
        if os.path.isdir(folder):
            for root, _dirs, files in os.walk(folder):
                if exe in files:
                    return os.path.join(root, exe)
    return None


def tool_install_hint(key):
    """User ko batayo kahan extract karna hai."""
    info = FREE_TOOLS.get(key)
    folder = os.path.join(TOOLS_DIR, key)
    return (
        f"{info[0]} abhi installed nahi hai.\n\n"
        f"1. Download page kholo: {info[2]}\n"
        f"2. Download karke extract karo is folder me:\n   {folder}\n"
        f"3. Phir dobara ye button dabao — tool khul jayega!"
    )


# ---- v8.6: Auto-download URLs (direct links) ----
# Sirf reliable direct URLs — GitHub releases waghera.
# Blogspot/MediaFire/Telegram wale yahan nahi (unreliable).
AUTO_DL_URLS = {
    # key: (direct_zip_url, exe_name_after_extract)
    "scrcpy": (
        "https://github.com/Genymobile/scrcpy/releases/latest/download/scrcpy-win64.zip",
        "scrcpy.exe",
    ),
}


def get_auto_dl_url(key):
    """Direct download URL hai to return karo, warna None."""
    return AUTO_DL_URLS.get(key)


def download_and_install(key, progress_callback=None):
    """Tool auto-download + extract karo. Returns (exe_path ya None, error_msg)."""
    import urllib.request
    import zipfile
    import shutil
    import tempfile

    dl_info = get_auto_dl_url(key)
    if not dl_info:
        return None, "Direct download available nahi"
    url, exe_name = dl_info
    folder = os.path.join(TOOLS_DIR, key)
    os.makedirs(folder, exist_ok=True)

    try:
        # Download with progress
        tmp = tempfile.mktemp(suffix=".zip")
        def hook(blocks, block_size, total):
            if progress_callback and total > 0:
                pct = min(100, int(blocks * block_size * 100 / total))
                progress_callback(pct)
        urllib.request.urlretrieve(url, tmp, reporthook=hook)

        # Extract
        with zipfile.ZipFile(tmp, 'r') as z:
            z.extractall(folder)
        os.remove(tmp)

        # EXE dhoondo
        exe = find_tool_exe(key)
        if exe:
            return exe, None
        return None, "EXE nahi mila extract ke baad"
    except Exception as exc:
        return None, str(exc)
