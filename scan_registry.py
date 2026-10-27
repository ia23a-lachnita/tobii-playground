#!/usr/bin/env python3
"""Find who populates the internal-stream-type registry at ctx+0x10e8
(count at ctx+0x14e8), and dump the GAZE_POINT wrapper 0x140276330 fully.
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


STR = {}
for m in re.finditer(rb"[\x20-\x7e]{4,}", d):
    r = f2r(m.start())
    if r is not None:
        STR.setdefault(IB + r, m.group().decode())

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
md.skipdata = True
tva, tvs, trp, trs = SECS[".text"]
CODE = list(md.disasm(d[trp:trp + trs], IB + tva))


def dis(a, b):
    o = r2f(a - IB)
    return list(md.disasm(d[o:o + b - a], a)) if o is not None else []


def show(il, label=""):
    if label:
        print("\n---- %s ----" % label)
    for ins in il:
        mark = ""
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            s = ins.operands[1]
            if s.type == X86_OP_MEM and s.mem.base == X86_REG_RIP:
                st = STR.get(ins.address + ins.size + s.mem.disp)
                if st:
                    mark = "   <<< %r" % st[:80]
        if ins.mnemonic in ("mov", "cmp", "add", "sub", "or", "and", "xor") and len(ins.operands) == 2:
            s = ins.operands[1]
            if s.type == X86_OP_IMM:
                mark = "   <<< imm 0x%x" % s.imm
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            mark = "   <<< call 0x%x" % ins.operands[0].imm
        if ins.mnemonic in ("jmp", "je", "jne", "ja", "jb", "jae", "jbe", "jg", "jl", "jge", "jle"):
            if ins.operands and ins.operands[0].type == X86_OP_IMM:
                mark = "   <<< -> 0x%x" % ins.operands[0].imm
        print("  0x%x  %-20s %s%s" % (ins.address, ins.mnemonic, ins.op_str, mark))


TARGETS = {0x10e8: "registry base (internal type array)",
           0x14e8: "registry count",
           0x1818: "caps array base (ctx+0xd8+0x1818)",
           0xa018: "caps array count (ctx+0xd8+0xa018)"}

print("== references to registry/caps displacements ==")
for ins in CODE:
    if ins.id == 0:
        continue
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.disp in TARGETS:
            print("  0x%x  %-18s %-32s  [%s]" %
                  (ins.address, ins.mnemonic, ins.op_str, TARGETS[op.mem.disp]))
            break

show(dis(0x140276330, 0x1402764f0), "GAZE_POINT wrapper 0x140276330 (full)")
show(dis(0x140273660, 0x140273a60), "general_stream_subscribe 0x140273660")
