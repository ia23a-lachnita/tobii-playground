#!/usr/bin/env python3
"""Find every site that writes the capability flags around ctx+0xa4f8..0xa5c0,
and dump the 4 thin wrappers that handle the primary gaze streams.

Usage: python scan_flags.py [exe]
"""
import re
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

PATH = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
IB = 0x140000000
d = open(PATH, "rb").read()
e = struct.unpack("<I", d[0x3C:0x40])[0]
coff = e + 4
nsec = struct.unpack("<H", d[coff + 2:coff + 4])[0]
so = coff + 20 + struct.unpack("<H", d[coff + 16:coff + 18])[0]
SECS = {}
for i in range(nsec):
    s = so + i * 40
    nm = d[s:s + 8].rstrip(b"\x00").decode("latin1")
    vs, va, rs, rp = struct.unpack("<IIII", d[s + 8:s + 24])
    SECS[nm] = (va, vs, rp, rs)


def r2f(rva):
    for nm, (va, vs, rp, rs) in SECS.items():
        if va <= rva < va + max(vs, rs):
            return rp + (rva - va)
    return None


def f2r(off):
    for nm, (va, vs, rp, rs) in SECS.items():
        if rp <= off < rp + rs:
            return va + (off - rp)
    return None


pva, pvs, prp, prs = SECS[".pdata"]
FUNCS = sorted((IB + b, IB + en) for b, en, _ in
               (struct.unpack("<III", d[prp + i * 12:prp + i * 12 + 12])
                for i in range(pvs // 12)))


def fbnd(va):
    lo, hi = 0, len(FUNCS) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        s, e2 = FUNCS[mid]
        if va < s:
            hi = mid - 1
        elif va >= e2:
            lo = mid + 1
        else:
            return (s, e2)
    return None


md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
md.skipdata = True

STR = {}
for m in re.finditer(rb"[\x20-\x7e]{4,}", d):
    r = f2r(m.start())
    if r is not None:
        STR.setdefault(IB + r, m.group().decode())

tva, tvs, trp, trs = SECS[".text"]
CODE = list(md.disasm(d[trp:trp + trs], IB + tva))


def disasm(a, b):
    o = r2f(a - IB)
    return list(md.disasm(d[o:o + b - a], a)) if o is not None else []


def show(il):
    for ins in il:
        mark = ""
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            s = ins.operands[1]
            if s.type == X86_OP_MEM and s.mem.base == X86_REG_RIP:
                st = STR.get(ins.address + ins.size + s.mem.disp)
                if st:
                    mark = "   <<< %r" % st[:90]
        if ins.mnemonic in ("mov", "cmp", "add", "sub") and len(ins.operands) == 2:
            dst, src = ins.operands
            if src.type == X86_OP_IMM:
                mark = "   <<< imm %d (0x%x)" % (src.imm, src.imm)
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            mark = "   <<< call 0x%x" % ins.operands[0].imm
        print("   0x%x  %-22s %s%s" % (ins.address, ins.mnemonic, ins.op_str, mark))


FLAGS = {0xa55c, 0xa558, 0xa560, 0xa5a8, 0xa5ac, 0xa590, 0xa594, 0xa598,
         0xa59c, 0xa5a0, 0xa584, 0xa588, 0xa5b0, 0xae34, 0x4d8, 0xce0}

print("== writes to ctx+0xa4f8..0xa5c0 flags ==")
for ins in CODE:
    if ins.id == 0:
        continue
    if ins.mnemonic != "mov" or len(ins.operands) != 2:
        continue
    dst, src = ins.operands
    if dst.type != X86_OP_MEM or src.type != X86_OP_IMM:
        continue
    disp = dst.mem.disp
    if disp in FLAGS:
        fb = fbnd(ins.address)
        print("\n  site 0x%x  fn %s   %s %s   (imm %d)" %
              (ins.address, ("0x%x..0x%x" % fb) if fb else "?", ins.mnemonic,
               ins.op_str, src.imm))
        if fb:
            il = disasm(fb[0], fb[1])
            idx = next((i for i, x in enumerate(il) if x.address == ins.address), None)
            if idx is not None:
                for x in il[max(0, idx - 12):idx + 4]:
                    print("      0x%x  %-20s %s" % (x.address, x.mnemonic, x.op_str))

print()
print("== thin wrappers (71-byte) full bodies ==")
for w in (0x140274ca0, 0x140274e50, 0x140275000, 0x140275e10, 0x140275fc0,
          0x1402764f0, 0x140276700, 0x1402768b0, 0x140276c20, 0x1402770b0,
          0x140277260, 0x140277410, 0x1402777e0, 0x140276dd0):
    b = fbnd(w)
    print("\n---- wrapper 0x%x fn 0x%x..0x%x ----" % (w, b[0], b[1]))
    show(disasm(b[0], b[1]))
