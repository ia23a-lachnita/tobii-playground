#!/usr/bin/env python3
"""Dump the descriptor-building helpers and the device::subscribe dispatch.

helpers: 0x140277a40, 0x140277ba0, 0x140277c20  -> build the 8-byte descriptor
          {byte0 = selector, dword+4 = requested INTERNAL stream type}
subscribe: function containing 0x1400f8552 ("Failed to subscribe to %s ...")

Usage: python dump_subscribe_dispatch.py [exe]
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


def disasm(a, b):
    o = r2f(a - IB)
    if o is None:
        return []
    return list(md.disasm(d[o:o + b - a], a))


def show(ins_list, tag=None):
    for ins in ins_list:
        mark = ""
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            src = ins.operands[1]
            if src.type == X86_OP_MEM and src.mem.base == X86_REG_RIP:
                s = STR.get(ins.address + ins.size + src.mem.disp)
                if s:
                    mark = "   <<< %r" % s[:100]
        if ins.mnemonic in ("mov", "cmp", "add", "sub") and len(ins.operands) == 2:
            dst, src = ins.operands
            if src.type == X86_OP_IMM:
                mark = "   <<< imm %d (0x%x)" % (src.imm, src.imm)
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            mark = "   <<< call 0x%x" % ins.operands[0].imm
        if ins.mnemonic == "mov" and len(ins.operands) == 2:
            dst, src = ins.operands
            if dst.type == X86_OP_MEM and "byte ptr" in ins.op_str:
                mark = "   <<< BYTE STORE %s" % ins.op_str
        line = "  0x%x  %-22s %s%s" % (ins.address, ins.mnemonic, ins.op_str, mark)
        if tag and tag not in line:
            continue
        print(line)


for h in (0x140277a40, 0x140277ba0, 0x140277c20):
    b = fbnd(h)
    lo = b[0] if b else h
    hi = b[1] if b else h + 0x60
    print("\n########## descriptor helper 0x%x (fn 0x%x..0x%x) ##########" %
          (h, lo, hi))
    show(disasm(lo, hi))

print("\n########## device::subscribe dispatch (0x1400f7040..0x1400f8480) ##########")
b = fbnd(0x1400f8552)
print("subscribe fn = 0x%x..0x%x" % (b[0], b[1]))
show(disasm(0x1400f77e0, 0x1400f7fa0))
print("   ...")
show(disasm(0x1400f82aa, 0x1400f83c0))
