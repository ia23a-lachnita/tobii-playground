#!/usr/bin/env python3
"""Revert the native x86 tobii_stream_engine.dll gaze_point_subscribe cave stub.

The stub redirected the internal stream id passed to the subscribe helper from
0 (TOBII_STREAM_GAZE_POINT) to 1 (TOBII_STREAM_GAZE_ORIGIN). The platform
runtime log proves the client therefore subscribed to PRP_STREAM_ENUM_GAZE_ORIGIN
and received zero-filled origin frames (validity=0, x=y=0) at the device frame
clock rate. Stream id 0 is correct as-is.

Sites (x86 file offsets):
  0x126bff..0x126c02  rel32 of the `call` at 0x126bfe  -> restore 5d a1 00 00
  0x126c34..0x126c3d  10-byte cave stub                -> restore cc padding
"""
import hashlib
import os
import shutil
import sys

APP = r"C:\Users\xursc\AppData\Local\TobiiGhost\app-1.14.1"
PRISTINE = r"C:\Users\xursc\Downloads\TobiiGhost_Extract\lib\native\x86\tobii_stream_engine.dll"
TARGETS = [
    os.path.join(APP, "tobii_stream_engine.dll"),
    os.path.join(APP, "x86", "tobii_stream_engine.dll"),
]

CALL_SITE = 0x126BFE
CAVE = 0x126C34
CAVE_LEN = 10

def main():
    pristine = open(PRISTINE, "rb").read()
    for path in TARGETS:
        if not os.path.exists(path):
            print("SKIP (missing):", path)
            continue
        data = bytearray(open(path, "rb").read())
        if len(data) != len(pristine):
            print("SKIP (size mismatch):", path, len(data), len(pristine))
            continue

        backup = path + ".backup_gazeroute"
        if not os.path.exists(backup):
            shutil.copy2(path, backup)

        # restore the call displacement
        orig_rel = pristine[CALL_SITE + 1:CALL_SITE + 5]
        cur_rel = bytes(data[CALL_SITE + 1:CALL_SITE + 5])
        changed_call = cur_rel != orig_rel
        data[CALL_SITE + 1:CALL_SITE + 5] = orig_rel

        # restore the cave to INT3 padding
        orig_cave = pristine[CAVE:CAVE + CAVE_LEN]
        cur_cave = bytes(data[CAVE:CAVE + CAVE_LEN])
        changed_cave = cur_cave != orig_cave
        data[CAVE:CAVE + CAVE_LEN] = orig_cave

        if not (changed_call or changed_cave):
            print("ALREADY PRISTINE:", path)
            continue

        open(path, "wb").write(bytes(data))
        print("REVERTED:", path)
        print("   call rel32:", cur_rel.hex(" "), "->", orig_rel.hex(" "))
        print("   cave     :", cur_cave.hex(" "), "->", orig_cave.hex(" "))
        print("   sha256   :", hashlib.sha256(bytes(data)).hexdigest()[:16])

    # consistency check
    hashes = []
    for path in TARGETS:
        if os.path.exists(path):
            hashes.append(hashlib.md5(open(path, "rb").read()).hexdigest())
    print("md5 of deployed copies:", hashes)
    print("MATCH" if len(hashes) == 2 and hashes[0] == hashes[1] else "MISMATCH")

if __name__ == "__main__":
    sys.exit(main())
