#!/usr/bin/env python3
"""Locate the writer(s) of the castor stream-type registry.

general_stream_subscribe (FUN_140273660) gates every stream on:
  registry A: int array at ctx+0x10e8, count at ctx+0x14e8
  registry B: 0x88-byte entries at ctx+0x18f0, count at ctx+0xa0f0
Both live in the SAME castor ctx object.

FUN_140263a90 already writes registry B (ctx+0x18f0 / ctx+0xa0f0).
This script finds who writes registry A (0x10e8 / 0x14e8).

File->VA mapping for platform_runtime_service.exe:
  .text va=0x1000 rp=0x400  =>  rva = file + 0xc00, VA = 0x140000000 + rva
"""
import re
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
d = open(PATH, "rb").read()

# disp32 encodings for the two offsets
A_DISP = bytes.fromhex("e8100000")   # 0x10e8
CNT_DISP = bytes.fromhex("e8140000")  # 0x14e8

# opcodes that plausibly READ/WRITE [reg+disp32]
#  89 r/m  = mov [r/m], reg      (write)
#  8b r/m  = mov reg, [r/m]      (read)
#  c7 r/m  = mov [r/m], imm32     (write)
#  83 r/m  = add/cmp [r/m], imm8  (write)
#  01 r/m  = add [r/m], reg      (write)
#  3b r/m  = cmp reg, [r/m]      (read)
#  39 r/m  = cmp [r/m], reg      (read)
#  8d r/m  = lea reg, [r/m]
#  0f b6/b7 r/m = movzx [r/m]
WRITE_OPS = {0x89, 0xC7, 0x83, 0x01, 0xFF, 0x09}
READ_OPS = {0x8B, 0x3B, 0x39, 0x8D, 0x0F, 0x03}


def va(off):
    return 0x140000000 + off + 0xC00


def scan(disp, label, limit=80):
    out = []
    start = 0
    while True:
        i = d.find(disp, start)
        if i < 0:
            break
        start = i + 1
        if not (0x400 <= i - 3 < len(d)):
            continue
        op = d[i - 3]
        modrm = d[i - 2]
        # only disp32 forms: mod != 0b11 (no disp8) and rex prefix present or op is c7/83
        if modrm & 0xC0 == 0xC0:
            continue
        if modrm & 0xC0 == 0x40:      # disp8 form -> disp32 not used
            continue
        out.append((i - 3, op, modrm))
    print("== %s : %d candidate sites ==" % (label, len(out)))
    seen = set()
    for off, op, modrm in out[:limit]:
        kind = "W" if op in WRITE_OPS else ("R" if op in READ_OPS else "?")
        ctx = d[off:off + 10].hex(" ")
        print("  file 0x%08x  VA 0x%x  op=%02x modrm=%02x  %s  bytes: %s"
              % (off, va(off), op, modrm, kind, ctx))
        seen.add(off)
    return out


w = scan(A_DISP, "0x10e8 (registry A payload)")
print()
c = scan(CNT_DISP, "0x14e8 (registry A count)")
print()
print("=== WRITE sites for registry A ===")
for off, op, modrm in w:
    if op in WRITE_OPS:
        print("  file 0x%08x  VA 0x%%x  op=%02x modrm=%02x bytes: %s"
              % (off, va(off), op, modrm, d[off:off + 14].hex(" ")))
print()
print("=== WRITE sites for registry A count ===")
for off, op, modrm in c:
    if op in WRITE_OPS:
        print("  file 0x%08x  VA 0x%x  op=%02x modrm=%02x bytes: %s"
              % (off, va(off), op, modrm, d[off:off + 14].hex(" ")))
