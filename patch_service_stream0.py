#!/usr/bin/env python3
"""Patch the Tobii Platform Runtime service so stream id 0 maps to the gaze handler.

Verified chain (Ghidra 12.1.4, rea MCP, platform_runtime_IS5LEYETRACKER5_service.exe):
  FUN_140264c90 = stream_type_receiver(stream_id_ptr RCX, dev_ctx RDX)
    0x140264c9f  MOV EAX, [RCX]          ; EAX = stream id
    0x140264ca7  CMP EAX, 1  / JNZ ...  ; dispatch ladder, EAX is not modified
    ...
    0x14026501e  CMP EAX, 5  / JNZ 0x1402650ef   <-- id-5 comparison slot
    0x140265027  XOR EDX,EDX / MOV RCX,RBX / CALL 0x140263a90   <-- gaze handler
                 (called with EDX = 0,1,2  -> registers gaze point/raw/origin)
    0x14026504b  CMP [RBX+0xa5b0],1 ; CMP [RBX+0xae34],1
                 -> with ae34 forced to 0 the capability entry IS appended
    0x140265284  default block: logs "Found unmapped stream %d" and returns

The 5L announces gaze as stream id 0.  Id 0 is not in the ladder, so it fell into
the default block, the gaze capability was never published and the client
subscribe failed with TOBII_ERROR_NOT_SUPPORTED (proved live, see FINDINGS.md).

Patch: ONE byte at VA 0x14026501e (file offset 0x264420)
    83 f8 05   CMP EAX, 5     ->   83 f8 00   CMP EAX, 0
  - id 0 now falls through into the id-5 handler at 0x140265027
  - every other id keeps its current behaviour
  - id 5 (never sent by the 5L) now ends up in the "unmapped" logger, which is
    harmless: the capability is already published by then.

Deliberately NOT done: jumping the whole default block to the gaze handler.
That would route every unmapped id into the gaze handler.  A 9-byte two-test
sequence in the comparison slot was also rejected: it overflows the 9-byte slot
by one byte and would clobber the handler's first instruction.

Usage
  python patch_service_stream0.py <path-to-platform_runtime_service.exe>
"""

import hashlib
import os
import shutil
import sys

OFF = 0x264420          # VA 0x14026501e (file = rva - 0xc00)
OLD = 0x05              # immediate of `CMP EAX, 5`
NEW = 0x00              # immediate of `CMP EAX, 0`
CTX_OFF = OFF - 2       # the `83 f8` opcode
CTX = bytes.fromhex("83f8050f85c800000033d2")   # CMP EAX,5 / JNZ +0xc8 / XOR EDX,EDX


def sha(data):
    return hashlib.sha256(data).hexdigest()[:16]


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: patch_service_stream0.py <service-exe>")
    exe = sys.argv[1]
    data = bytearray(open(exe, "rb").read())

    if len(data) < OFF + 1:
        raise SystemExit("[!] file too small")

    ctx = bytes(data[CTX_OFF:CTX_OFF + len(CTX)])
    if ctx != CTX:
        raise SystemExit("[!] ABORT: signature mismatch at 0x%x:\n    got      %s\n"
                         "    expected %s" % (CTX_OFF, ctx.hex(" "), CTX.hex(" ")))

    if data[OFF] == NEW:
        print("ALREADY PATCHED: %s (sha %s)" % (exe, sha(bytes(data))))
        return

    if data[OFF] != OLD:
        raise SystemExit("[!] ABORT: expected 0x%02x at 0x%x, found 0x%02x"
                         % (OLD, OFF, data[OFF]))

    bak = exe + ".bak_stream0"
    if not os.path.exists(bak):
        shutil.copy2(exe, bak)
        print("[ok] backup -> %s" % bak)

    data[OFF] = NEW
    open(exe, "wb").write(bytes(data))

    chk = open(exe, "rb").read()
    if chk[OFF] != NEW:
        raise SystemExit("[!] verification after write failed")
    print("[ok] patched %s" % exe)
    print("    file 0x%x: 83 f8 %02x -> 83 f8 %02x   (CMP EAX,5 -> CMP EAX,0)"
          % (OFF, OLD, NEW))
    print("    sha now %s" % sha(chk))
    print("[ok] stream 0 now routes into the gaze handler at VA 0x140265027")


if __name__ == "__main__":
    main()
