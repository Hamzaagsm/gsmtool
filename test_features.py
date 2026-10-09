"""Offline tests for features.py parsers -- no phone needed."""

from features import (
    find_suspicious_packages,
    find_transsion_id_packages,
    imei_at_commands,
    parse_adb_devices,
    parse_device_admins,
    parse_fastboot_devices,
    parse_packages,
    validate_imei,
)

ADB_SAMPLE = """List of devices attached
8f9a2c1\tdevice product:noteedge model:X6887 device:edge
emulator-5554\tunauthorized
"""

assert parse_adb_devices(ADB_SAMPLE) == [
    ("8f9a2c1", "device"),
    ("emulator-5554", "unauthorized"),
]
assert parse_adb_devices("List of devices attached\n\n") == []

FB_SAMPLE = "8f9a2c1\tfastboot\n"
assert parse_fastboot_devices(FB_SAMPLE) == ["8f9a2c1"]

PKG_SAMPLE = """package:com.android.settings
package:com.transsion.mdm.agent
package:com.google.android.gms
"""
pkgs = parse_packages(PKG_SAMPLE)
assert pkgs == ["com.android.settings", "com.transsion.mdm.agent",
                "com.google.android.gms"]
assert find_suspicious_packages(pkgs) == ["com.transsion.mdm.agent"]
assert find_suspicious_packages(["com.android.chrome"]) == []

DUMPSYS_SAMPLE = """
Active admin ComponentInfo{com.transsion.mdm.agent/.AdminReceiver}:
  ...
Active password quality: 0
"""
assert parse_device_admins(DUMPSYS_SAMPLE) == [
    "com.transsion.mdm.agent/.AdminReceiver"
]
assert parse_device_admins("no admins here") == []

TRANSSION_SAMPLE = [
    "com.transsion.idlock",
    "com.android.settings",
    "com.transsion.account",
    "com.google.android.gms",
]
assert find_transsion_id_packages(TRANSSION_SAMPLE) == [
    "com.transsion.idlock",
    "com.transsion.account",
]
assert find_transsion_id_packages(["com.android.chrome"]) == []
assert find_transsion_id_packages([]) == []

# ---- IMEI validation (original-restore only; no generator exists) ----
ok, clean = validate_imei("490154203237518")  # classic valid example IMEI
assert ok and clean == "490154203237518"
ok, clean = validate_imei(" 490154203237518 ")  # spaces tolerated
assert ok and clean == "490154203237518"
ok, _ = validate_imei("490154203237519")  # bad checksum
assert not ok
ok, _ = validate_imei("49015420323751")  # 14 digits
assert not ok
ok, _ = validate_imei("4901542032375181")  # 16 digits
assert not ok
ok, _ = validate_imei("49015420323751A")  # non-digit
assert not ok
ok, _ = validate_imei("")  # empty
assert not ok
ok, _ = validate_imei(None)
assert not ok

c1, c2 = imei_at_commands("490154203237518")
assert c1 == 'AT+EGMR=1,7,"490154203237518"'
assert c2 == 'AT+EGMR=1,10,"490154203237518"'

print("All parser tests passed.")
