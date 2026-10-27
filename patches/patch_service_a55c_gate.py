#!/usr/bin/env python3
"""Patch the Tobii Platform Runtime service to un-gate stream registrations.

Background:
  When client requests PRP_STREAM_ENUM_GAZE_POINT, the service checks if
  internal stream type 4 is registered in the context's stream table at [rbx+0x10e8].
  Stream type 4 is ONLY registered in the id==1 block in stream_type_receiver (0x140264c90)
  under the condition [rbx+0xa55c] == 1:
      0x140264cf9: cmp dword ptr [rbx + 0xa55c], 1
      0x140264d00: jne 0x140264d49   (file offset 0x264100: 75 47)
  Since the 5L device does not set ctx+0xa55c to 1, this jump skips type 4 registration,
  causing general_stream_subscribe (0x140273660) to fail with error 3 (PLATMOD_ERROR_NOT_SUPPORTED).

Patches applied:
  1. 0x264100 (VA 0x140264d00): 75 47 -> 90 90 (un-gate type 4 GAZE_POINT)
  2. 0x264150 (VA 0x140264d50): 75 47 -> 90 90 (un-gate type 0x1d RESPONSIVE_GAZE_POINT)
  3. 0x272ae7 (VA 0x1402736e7): 75 40 -> eb 40 (force general_stream_subscribe to accept)
"""

import hashlib
import os
import shutil
import sys

PATCHES = [
    {
        "name": "a55c gate (stream 4 GAZE_POINT registration)",
        "va": 0x140264d00,
        "offset": 0x264100,
        "sig_off": 0x2640f9,
        "expected_sig": bytes.fromhex("83bb5ca50000017547488b4308"),
        "old_bytes": bytes.fromhex("7547"),
        "new_bytes": bytes.fromhex("9090"),
    },
    {
        "name": "a560 gate (stream 0x1d RESPONSIVE_GAZE_POINT registration)",
        "va": 0x140264d50,
        "offset": 0x264150,
        "sig_off": 0x264149,
        "expected_sig": bytes.fromhex("83bb60a50000017547488b4308"),
        "old_bytes": bytes.fromhex("7547"),
        "new_bytes": bytes.fromhex("9090"),
    },
    {
        "name": "general_stream_subscribe validation bypass",
        "va": 0x1402736e7,
        "offset": 0x272ae7,
        "sig_off": 0x272ae3,
        "expected_sig": bytes.fromhex("32c084c07540b803000000"),
        "old_bytes": bytes.fromhex("7540"),
        "new_bytes": bytes.fromhex("eb40"),
    },
]


def sha(data):
    return hashlib.sha256(data).hexdigest()[:16]


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
    if not os.path.exists(target):
        raise SystemExit(f"[!] Target {target} not found")

    with open(target, "rb") as f:
        data = bytearray(f.read())

    print(f"Target: {target} (size: {len(data)}, sha16: {sha(data)})")

    # Verify all signatures first
    for p in PATCHES:
        sig_len = len(p["expected_sig"])
        found_sig = bytes(data[p["sig_off"]:p["sig_off"] + sig_len])
        if found_sig != p["expected_sig"]:
            # Check if already patched
            patched_sig = bytearray(p["expected_sig"])
            rel = p["offset"] - p["sig_off"]
            patched_sig[rel:rel + len(p["new_bytes"])] = p["new_bytes"]
            if found_sig == bytes(patched_sig):
                print(f"  [-] {p['name']} already patched.")
                continue
            raise SystemExit(
                f"[!] Signature mismatch for {p['name']} at 0x{p['sig_off']:x}:\n"
                f"    found:    {found_sig.hex(' ')}\n"
                f"    expected: {p['expected_sig'].hex(' ')}"
            )

    # Backup
    bak = target + ".bak_a55c"
    if not os.path.exists(bak):
        shutil.copy2(target, bak)
        print(f"[ok] Created backup: {bak}")

    # Apply patches
    modified = False
    for p in PATCHES:
        curr = bytes(data[p["offset"]:p["offset"] + len(p["new_bytes"])])
        if curr == p["new_bytes"]:
            continue
        data[p["offset"]:p["offset"] + len(p["new_bytes"])] = p["new_bytes"]
        print(f"  [+] Patched {p['name']} at file 0x{p['offset']:x} (VA 0x{p['va']:x}): {curr.hex()} -> {p['new_bytes'].hex()}")
        modified = True

    if modified:
        with open(target, "wb") as f:
            f.write(data)
        print(f"[ok] Successfully wrote patched binary. New sha16: {sha(data)}")
    else:
        print("[*] All patches already applied, nothing to do.")


if __name__ == "__main__":
    main()
