#!/usr/bin/env python3
"""Patch the x86 Stream Engine subscribe gate: ignore the internal
stream_supported verdict inside the subscribe wrapper.

WHY
---
`tobii_gaze_point_subscribe` does NOT go through the public export
`tobii_stream_supported` (which we already force to true).  It calls the
INTERNAL gate directly:

    FUN_10131960 (file 0x130d60, VA 0x10131960)
      0x10131a04  CALL 0x1012e170        ; internal stream_supported
                                          ; (FUN_1012e170, file 0x12d570)
      0x10131a09  TEST AL, AL
      0x10131a0b  JNZ 0x10131a53        ; -> supported path
      ...                                 ; error path: code 3
                                          ; = TOBII_ERROR_NOT_SUPPORTED

FUN_1012e170 returns FALSE on this device because the client's capability
array at [ctx+0x4d8] is NULL, so its FALLBACK branch is taken and the gaze
stream ids (0/1/2/5) are not found in the local arrays.  The subscribe then
fails with TOBII_ERROR_NOT_SUPPORTED even though the public export says the
stream is supported (live evidence: managed probe reports
`SubscribeToGazePoints -> TOBII_ERROR_NOT_SUPPORTED` while
`IsStreamSupported(GAZE_POINT) == True`).

PATCH (1 byte)
--------------
    file 0x130e0b:  75 46   JNZ +0x46     ->   EB 46   JMP +0x46

`JNZ short` and `JMP short` are both 2 bytes with the same rel8
displacement, so the target (0x10131a53, the supported path) is unchanged.
No call/ret is touched => the stack stays balanced, and no register is
clobbered.  On this device the gate returns false for EVERY stream id
(the capability array is NULL), so forcing the supported path is equivalent
to a per-stream conditional and cannot enable anything that was previously
reachable.

Antigravity second opinion (2026-10-26): recommended exactly this 1-byte
change over a code-cave entry redirect (which had crashed in an earlier
attempt).

Usage
  python patch_x86_subscribe_gate.py <path-to-tobii_stream_engine.dll>
"""

import hashlib
import os
import shutil
import sys

# CALL 0x1012e170 ; TEST AL,AL ; JNZ +0x46
SIG_OFF = 0x130E04
SIG = bytes.fromhex("e867c7ffff84c07546")
# the branch opcode itself
BRANCH_OFF = 0x130E0B
OLD = 0x75          # JNZ rel8
NEW = 0xEB          # JMP rel8  (same displacement, same length)


def sha(data):
    return hashlib.sha256(data).hexdigest()[:16]


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: patch_x86_subscribe_gate.py <dll>")
    path = sys.argv[1]
    with open(path, "rb") as f:
        data = bytearray(f.read())

    sig = bytes(data[SIG_OFF:SIG_OFF + len(SIG)])
    if sig != SIG:
        raise SystemExit("[!] ABORT: signature mismatch at 0x%x\n"
                         "    got      %s\n    expected %s"
                         % (SIG_OFF, sig.hex(" "), SIG.hex(" ")))

    if data[BRANCH_OFF] == NEW:
        print("ALREADY PATCHED: %s (sha %s)" % (path, sha(bytes(data))))
        return 0
    if data[BRANCH_OFF] != OLD:
        raise SystemExit("[!] ABORT: expected 0x%02x at 0x%x, found 0x%02x"
                         % (OLD, BRANCH_OFF, data[BRANCH_OFF]))

    bak = path + ".bak_gate"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print("[ok] backup -> %s" % bak)

    data[BRANCH_OFF] = NEW
    with open(path, "wb") as f:
        f.write(bytes(data))

    with open(path, "rb") as f:
        chk = f.read()
    if chk[BRANCH_OFF] != NEW:
        raise SystemExit("[!] verification after write failed")
    print("[ok] patched %s" % path)
    print("    file 0x%x: %02x -> %02x   (JNZ +0x46 -> JMP +0x46)"
          % (BRANCH_OFF, OLD, NEW))
    print("    sha now %s" % sha(chk))
    print("[ok] the subscribe path now ignores the internal stream_supported verdict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
