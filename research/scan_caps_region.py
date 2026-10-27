#!/usr/bin/env python3
"""Find writers of the castor capability-flag region (ctx+0xa500..0xa5c0).

The caps struct lives at ctx+0xa4f8 (see FUN_140263a90: lVar4 = ctx+0xa4f8 and
it reads lVar4+0x30/+0x34/+0x40/+0x44/+0x48).  The flags that gate registry-A
publication are:
    ctx+0xa558 -> internal type 0x21 (Absolute Eye Openness)
    ctx+0xa55c -> internal type 4    (Gaze Point)          <-- the one we need
    ctx+0xa560 -> internal type 0x1d (Responsive Gaze Point)

This scan lists EVERY instruction in .text that touches an offset in
[0xa500, 0xa5c0] of a ctx-like base, with read/write classification, so the
writer of 0xa55c can be identified.

Usage: python scan_caps_region.py [path-to-exe]
"""
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_MEM, X86_OP_REG

PATH = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
IMAGEBASE = 0x140000000
LO, HI = 0xA500, 0xA5C0

d = open(PATH, "rb").read()
e = struct.unpack("<I", d[0x3C:0x40])[0]
coff = e + 4
nsec = struct.unpack("<H", d[coff + 2:coff + 4])[0]
so = coff + 20 + struct.unpack("<H", d[coff + 16:coff + 18])[0]
for i in range(nsec):
    s = so + i * 40
    nm = d[s:s + 8].rstrip(b"\x00").decode("latin1")
    vs, va, rs, rp = struct.unpack("<IIII", d[s + 8:s + 24])
    if nm.startswith(".text"):
        tva, trp, trs = va, rp, rs

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
md.skipdata = True

WRITE_MNEM = {"mov", "movaps", "movups", "movdqa", "movdqu", "stos", "xchg",
              "add", "sub", "or", "and", "inc", "dec", "shl", "shr"}
rows = []
for ins in md.disasm(d[trp:trp + trs], IMAGEBASE + tva):
    if ins.id == 0:
        continue
    for op in ins.operands:
        if op.type != X86_OP_MEM:
            continue
        disp = op.mem.disp
        if not (LO <= disp <= HI):
            continue
        if op.mem.base == 0:
            continue
        kind = "W" if ins.mnemonic in WRITE_MNEM and op.access else (
            "R" if op.access == 1 else "RW")
        rows.append((ins.address, disp, kind, ins.mnemonic, ins.op_str))
        break

print("%d instructions touch ctx+0x%x..0x%x" % (len(rows), LO, HI))
print("\n== by offset ==")
by = {}
for a, disp, kind, m, o in rows:
    by.setdefault(disp, []).append((a, kind, m, o))
for disp in sorted(by):
    lst = by[disp]
    w = [x for x in lst if x[1] == "W"]
    print("\n ctx+0x%x : %d refs (%d writes)" % (disp, len(lst), len(w)))
    for a, kind, m, o in lst[:12]:
        print("   VA 0x%x  %-3s %-8s %s" % (a, kind, m, o))
