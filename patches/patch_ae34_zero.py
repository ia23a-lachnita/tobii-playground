"""patch_ae34_zero.py — force the service's platform-classifier field ctx+0xae34 to 0.

WHY (evidence, 2026-10-23)
--------------------------
The platform runtime classifies the attached device into a platform bucket that
is stored at ctx+0xae34:

    0 (other / desktop flat-display), 1 ("HMD" class), 2 ("Internal_display")

The capability-registration routine (stream_type_receiver) appends the GAZE
capability entry to the announced stream list ONLY when

    NOT (ctx+0xa5b0 == 1 && ctx+0xae34 == 1)

Every single access to ctx+0xae34 in the whole image (verified by scanning for
the 0xae34 displacement bytes) is a `cmp dword ptr [reg+0xae34], 1` test, and
there is exactly ONE store — file offset 0x26369a:

    89 be 34 ae 00 00    mov [rsi+0xae34], edi

LIVE SYMPTOM with ae34 forced to 1:
  * client subscribe for GAZE_POINT (public stream id 0) -> TOBII_ERROR_NOT_SUPPORTED
    and the service logs no successful subscription for it;
  * the only stream served is GAZE_ORIGIN ("Gaze Origin does not need any
    specific avilability check") which delivers zero-filled, INVALID payloads
    on a flat display;
  * the device itself advertises stream/capability id 5 = true (gaze present),
    so the refusal is a host-side classification decision, not a device gap.

The 5L is a flat-panel tracker and needs the desktop bucket (ae34 = 0).

PATCH
-----
File offset 0x263692, 14-byte window, currently:

    bf 01 00 00 00 89 be 34 ae 00 00 90 90 90
    (mov edi,1 ; mov [rsi+0xae34],edi ; nops)

becomes:

    bf 00 00 00 00 89 be 34 ae 00 00 90 90 90
    (mov edi,0 ; mov [rsi+0xae34],edi ; nops)

The unconditional store is kept, so the field is written exactly once with a
compile-time constant and no later write can overwrite it (there is no other
store anywhere in the image). The HMD-exact-match JMP NOP at file offset
0x26367D (EB 1B -> 90 90) MUST stay: with the force patch in place the JMP
target 0x26369a no longer lands on an instruction boundary, so leaving the
JMP intact would corrupt control flow.

Byte-compare guards make the patch idempotent and abort on any mismatch.
"""

import hashlib
import os
import sys

EXE = "platform_runtime_service.exe"
BACKUP = EXE + ".bak_ae34zero"

# force-write window (14 bytes)
FORCE_OFF = 0x263692
OLD_FORCE = bytes.fromhex("bf0100000089be34ae0000909090")
NEW_FORCE = bytes.fromhex("bf0000000089be34ae0000909090")

# HMD-exact-match JMP NOP (2 bytes) — must already be applied
HMDJMP_OFF = 0x26367D
OLD_HMD = bytes.fromhex("eb1b")
NEW_HMD = bytes.fromhex("9090")


def main():
    dry = "--dry-run" in sys.argv
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), EXE)
    with open(path, "rb") as f:
        data = bytearray(f.read())

    cur_force = bytes(data[FORCE_OFF:FORCE_OFF + len(OLD_FORCE)])
    cur_hmd = bytes(data[HMDJMP_OFF:HMDJMP_OFF + len(OLD_HMD)])

    if cur_hmd not in (OLD_HMD, NEW_HMD):
        print(f"ABORT: HMD JMP bytes at 0x{HMDJMP_OFF:x} = {cur_hmd.hex(' ')} "
              f"(expected eb 1b or 90 90)")
        return 1
    if cur_hmd == OLD_HMD:
        print(f"ABORT: HMD JMP NOP at 0x{HMDJMP_OFF:x} is missing — the force patch "
              f"would break control flow. Apply patch_ae34_hmd.py first.")
        return 1

    if cur_force == NEW_FORCE:
        print("ALREADY PATCHED: ae34 force = 0")
        return 0
    if cur_force != OLD_FORCE:
        print(f"ABORT: bytes at 0x{FORCE_OFF:x} = {cur_force.hex(' ')}")
        print(f"      expected {OLD_FORCE.hex(' ')} (ae34=1 force) or "
              f"{NEW_FORCE.hex(' ')} (already ae34=0)")
        return 1

    if dry:
        print(f"DRY RUN OK: would patch 0x{FORCE_OFF:x}: "
              f"{OLD_FORCE.hex(' ')} -> {NEW_FORCE.hex(' ')}")
        return 0

    with open(path + ".bak_ae34zero", "wb") as f:
        f.write(data)
    data[FORCE_OFF:FORCE_OFF + len(OLD_FORCE)] = NEW_FORCE
    with open(path, "wb") as f:
        f.write(bytes(data))

    print(f"patched 0x{FORCE_OFF:x}: {OLD_FORCE.hex(' ')} -> {NEW_FORCE.hex(' ')}")
    print("backup:", path + ".bak_ae34zero")
    print("sha256:", hashlib.sha256(bytes(data)).hexdigest())
    print("deploy: stop TobiiPlatformRuntime, copy to "
          r'"C:\Program Files\Tobii\Platform Runtime\platform_runtime_IS5LEYETRACKER5_service.exe", '
          "start service")
    return 0


if __name__ == "__main__":
    sys.exit(main())
