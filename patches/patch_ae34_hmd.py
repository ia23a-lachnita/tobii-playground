"""patch_ae34_hmd.py — stop the service from classing the 5L as HMD.

Root cause chain (proven 2026-10-18, see HANDOFF.md):

setup_device_info (FUN_1402640d0) reads the device-info TTP response
(op 0x354) and computes ctx->ae34:

    if (info+0x78 == 0) { fail("Could not get integration type"); }  // live: not taken
    strncpy(ctx+0xaa34, info, 0xff);
    edi = 1;                                   // 0x140264113: MOV EDI, 1
    // 4-byte compare against "HMD\0" (DAT_140469660):
    if (ctx[0..3] == "HMD\\0") goto write;      // 0x14026427d: JMP 0x14026429a (EB 1B)
    edi = strcmp(ctx, "Internal_display") == 0 ? 2 : 0;
write:
    ctx->ae34 = edi;                           // 0x14026429a

stream_type_receiver (FUN_140264c90) appends the gaze capability entry
{3, 0x10, 0x11, 1} (ctx+0x18f0 array, count ctx+0xa0f0) ONLY when
!(ctx->a5b0 == 1 && ctx->ae34 == 1). Live log shows a5b0 == 1, so a
device reporting integration type exactly "HMD" gets ae34 == 1 -> gaze
entry skipped -> Ghost: "We only discovered devices that doesn't support
eyetracking".

Patch: NOP the HMD-match JMP (VA 0x14026427d, file 0x26367D, bytes EB 1B)
so an exact-"HMD" device falls through into the normal classify path:
strcmp(info, "Internal_display") != 0 -> EDI = 0 -> ae34 = 0 -> gaze
capability announced. Instruction context (verified bytes):

    75 E3        JNZ loop
    EB 1B        JMP 0x14026429a      <- patched to 90 90
    48 8D 15 ..  LEA RDX, "Internal_display"

Semantics after patch: "HMD" -> ae34 0 (identical to any unknown
integration type; the only consumer of ae34 tests == 1). No other code
path is touched.
"""

import sys

EXE = "platform_runtime_service.exe"
BACKUP = EXE + ".bak_hmd313"

# Patch site: VA 0x14026427d, resolved by rea address_to_file_offset.
FILE_OFFSET = 0x26367D
OLD_BYTES = bytes.fromhex("eb1b")
NEW_BYTES = bytes.fromhex("9090")

# Unique surrounding signature (75 E3 EB 1B 48 8D 15 ...) — location check.
SIG = bytes.fromhex("75e3eb1b488d15")


def main():
    dry = "--dry-run" in sys.argv
    with open(EXE, "rb") as f:
        data = bytearray(f.read())

    # 1. Locate by unique signature, require exactly one hit.
    hits = []
    start = 0
    while True:
        i = data.find(SIG, start)
        if i < 0:
            break
        hits.append(i)
        start = i + 1
    if len(hits) != 1:
        print(f"ABORT: signature hits = {len(hits)} (expected 1): {[hex(h) for h in hits]}")
        return 1
    sig_at = hits[0]

    # 2. The EB 1B must sit exactly at signature offset +2.
    jmp_at = sig_at + 2
    if jmp_at != FILE_OFFSET:
        print(f"note: signature implies JMP at 0x{jmp_at:x}, expected 0x{FILE_OFFSET:x}"
              f" (delta {jmp_at - FILE_OFFSET:+d}) — using signature location")

    # 3. Verify the bytes we are about to change.
    cur = bytes(data[jmp_at:jmp_at + len(OLD_BYTES)])
    if cur != OLD_BYTES:
        print(f"ABORT: bytes at 0x{jmp_at:x} = {cur.hex()} (expected {OLD_BYTES.hex()})")
        print("      already patched or wrong binary — restore backup first")
        return 1

    if dry:
        print(f"DRY RUN OK: would patch 0x{jmp_at:x}: {OLD_BYTES.hex()} -> {NEW_BYTES.hex()}")
        return 0

    with open(BACKUP, "wb") as f:
        f.write(data)
    data[jmp_at:jmp_at + len(OLD_BYTES)] = NEW_BYTES
    with open(EXE, "wb") as f:
        f.write(data)

    print(f"patched 0x{jmp_at:x}: {OLD_BYTES.hex()} -> {NEW_BYTES.hex()}")
    print(f"backup: {BACKUP}")
    print("verify: search for 90 90 48 8d 15 (need exactly one hit) and confirm"
          " EB 1B no longer precedes an LEA RDX")
    return 0


if __name__ == "__main__":
    sys.exit(main())
