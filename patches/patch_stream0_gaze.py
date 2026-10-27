#!/usr/bin/env python3
"""Patch: route unmapped stream id 0 into the stream-5 (gaze) handler.

Verified chain (Ghidra, platform_runtime_service.exe, PE x86_64):
  FUN_140264c90 = stream_type_receiver(stream_id_ptr RCX, dev_ctx RDX)
  Mapped ids: 1,2,3,4,5,7,9,0xc,0xd,0xe,0xf,0x10,0x11,0x12,0x15.
  Stream 5 (gaze, wire id 0x0500 on the 5L) handler block starts at VA 0x14026501e
    (XOR EDX,EDX / MOV RCX,RBX / CALL FUN_140263a90 ...) and appends the gaze
    capability entries.
  Default (unmapped) block starts at VA 0x140265284:
    LEA RDI,[0x1404696a0]  ->  48 8D 3D 15 3D 20 00
    ... strlen/strnlen on the source-file string, then the
    "Found unmapped stream 0" log call (0x1403ac460) and RET.
    Single jump target from the dispatch chain (JNZ at VA 0x14026525a).

Patch: overwrite the first 5 bytes of the default block with
    E9 95 FD FF FF   ; JMP 0x14026501e (stream-5 handler)
The two trailing LEA bytes remain in the file but are never executed
(the default block is only entered via that one jump).
  next RIP = 0x140265289 ; rel32 = 0x14026501e - 0x140265289 = -0x26B
  => E9 95 FD FF FF

Live verification after deploy: the "Found unmapped stream 0" warning
disappears from pr_log0.txt on device plug-in.

Backup: platform_runtime_service.exe.bak_stream0 (created on first run).
"""

import sys

EXE = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
BAK = EXE + ".bak_stream0"

OFF = 0x264684           # VA 0x140265284 (delta 0x1400AAC0)
OLD = bytes.fromhex("488d3d153d2000")   # LEA RDI,[0x1404696a0] (idents default block)
NEW = bytes.fromhex("e995fdffff")       # JMP 0x14026501e

def main():
    try:
        with open(EXE, "rb") as f:
            data = bytearray(f.read())
    except OSError as e:
        sys.exit(f"[!] cannot read {EXE}: {e}")

    if len(data) < OFF + len(OLD):
        sys.exit(f"[!] file too small ({len(data)} bytes)")

    cur = bytes(data[OFF:OFF + len(OLD)])
    if cur == NEW[:5] + OLD[5:]:
        sys.exit("ALREADY PATCHED - nothing to do")
    if cur != OLD:
        sys.exit(f"ABORT: default-block signature mismatch at 0x{OFF:x}: {cur.hex()} (expected {OLD.hex()})")

    try:
        with open(BAK, "wb") as f:
            f.write(data)
        print(f"[ok] backup -> {BAK}")
    except OSError as e:
        sys.exit(f"[!] cannot write backup: {e}")

    data[OFF:OFF + 5] = NEW
    with open(EXE, "wb") as f:
        f.write(data)

    # re-read and verify
    with open(EXE, "rb") as f:
        chk = f.read()
    if chk[OFF:OFF + 5] != NEW:
        sys.exit("ERROR: verification after write failed")
    print(f"[ok] patched 0x{OFF:x}: {OLD[:5].hex()} -> {NEW.hex()}")
    print(f"[ok] stream 0 now routes into the stream-5 gaze handler (VA 0x14026501e)")
    print(f"[ok] unmapped-stream warning will be gone from pr_log0.txt after replug")

if __name__ == "__main__":
    main()
