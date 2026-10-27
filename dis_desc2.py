#!/usr/bin/env python3
"""For every general_stream_subscribe call site, extract:
  * every immediate STORE into memory in the preceding 0x140 bytes
  * every RIP-relative LEA that resolves to an ASCII string

The stream descriptor passed as param_4 holds:
    byte  [0] = registry selector (0 -> registry A ctx+0x10e8, else registry B)
    dword [4] = requested INTERNAL stream type
so the small immediate stores right before the call reveal the internal type.

Usage: python dis_desc2.py [path-to-exe]
"""
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM

PATH = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
IMAGEBASE = 0x140000000
TARGET = 0x140273660

CALLERS = [0x140274ae0, 0x140274ca0, 0x140274e50, 0x140275000, 0x1402751a0,
           0x140275360, 0x140275520, 0x140275e10, 0x140275fc0, 0x140276170,
           0x140276330, 0x1402764f0, 0x140276700, 0x1402768b0, 0x140276a60,
           0x140276c20, 0x140276dd0, 0x1402770b0, 0x140277260, 0x140277410,
           0x1402777e0]

d = open(PATH, "rb").read()
e = struct.unpack("<I", d[0x3C:0x40])[0]
coff = e + 4
nsec = struct.unpack("<H", d[coff + 2:coff + 4])[0]
so = coff + 20 + struct.unpack("<H", d[coff + 16:coff + 18])[0]
SECS = []
for i in range(nsec):
    s = so + i * 40
    nm = d[s:s + 8].rstrip(b"\x00").decode("latin1")
    vs, va, rs, rp = struct.unpack("<IIII", d[s + 8:s + 24])
    SECS.append((nm, va, vs, rp, rs))


def rva2file(rva):
    for nm, va, vs, rp, rs in SECS:
        if va <= rva < va + max(vs, rs):
            return rp + (rva - va)
    return None


def cstr(rva, maxlen=100):
    off = rva2file(rva)
    if off is None:
        return None
    end = d.find(b"\x00", off, off + maxlen)
    if end < 0:
        return None
    raw = d[off:end]
    if not raw:
        return None
    try:
        s = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    return s if all(32 <= ord(c) < 127 for c in s) else None


md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
md.skipdata = True

for c in CALLERS:
    start = c - 0x140
    fo = (start - IMAGEBASE) - 0xC00
    insns = list(md.disasm(d[fo:fo + 0x160], start))
    stores, strs = [], []
    for ins in insns:
        if ins.address > c:
            break
        if ins.mnemonic == "mov" and len(ins.operands) == 2:
            dst, src = ins.operands
            if dst.type == X86_OP_MEM and src.type == X86_OP_IMM:
                if src.imm <= 0x400:
                    b = ins.reg_name(dst.mem.base) if dst.mem.base else "-"
                    stores.append((ins.address, b, dst.mem.disp, src.imm))
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            dst, src = ins.operands
            if src.type == X86_OP_MEM and src.mem.base == 0 and src.mem.disp:
                s = cstr(src.mem.disp - IMAGEBASE)
                if s:
                    strs.append((ins.address, s))
    print("\n=== call site 0x%x ===" % c)
    for a, b, disp, imm in stores[-14:]:
        print("   store 0x%x  [%s+0x%x] = %d (0x%x)" % (a, b, disp, imm, imm))
    for a, s in strs[-6:]:
        print("   str   0x%x  %r" % (a, s[:80]))
