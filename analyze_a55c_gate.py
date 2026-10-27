#!/usr/bin/env python3
"""Analyse the ctx+0xa55c gate that registers internal stream type 4 ('Gaze Point').

Questions answered:
 1. What exactly does the a55c==1 branch do (fall-through) vs the jne target?
 2. Who writes ctx+0xa55c? (direct imm store / indexed store / memcpy source)
 3. Exact byte signature of the gate for patching.
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


def show(a, b, label=""):
    if label:
        print("\n---- %s ----" % label)
    for ins in dis(a, b):
        mk = ""
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            s = ins.operands[1]
            if s.type == X86_OP_MEM and s.mem.base == X86_REG_RIP:
                st = STR.get(ins.address + ins.size + s.mem.disp)
                if st:
                    mk = "   <<< %r" % st[:90]
        if ins.mnemonic in ("mov", "cmp", "add", "sub", "or", "and", "xor", "test") and len(ins.operands) == 2:
            s = ins.operands[1]
            if s.type == X86_OP_IMM:
                mk = "   <<< imm 0x%x" % s.imm
            if s.type == X86_OP_MEM:
                mk += "  disp=0x%x index=%s" % (s.mem.disp, s.mem.index)
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            mk = "   <<< call 0x%x" % ins.operands[0].imm
        if ins.mnemonic.startswith("j") and ins.operands and ins.operands[0].type == X86_OP_IMM:
            mk = "   <<< -> 0x%x" % ins.operands[0].imm
        print("  0x%x  %-18s %-42s%s" % (ins.address, ins.mnemonic, ins.op_str, mk))


print("=" * 78)
print("1) GATE REGION 0x140264cf0..0x140264d90")
print("=" * 78)
show(0x140264cf0, 0x140264d90)

print()
print("=" * 78)
print("2) ALL WRITES whose mem disp lands in ctx+0xa4f8..0xa5c0")
print("=" * 78)
for ins in CODE:
    if ins.id == 0 or ins.mnemonic not in ("mov", "or", "and", "add", "sub", "xor"):
        continue
    if not ins.operands:
        continue
    dst = ins.operands[0]
    if dst.type != X86_OP_MEM:
        continue
    if not (0xa4f8 <= dst.mem.disp <= 0xa5c0):
        continue
    src = ins.operands[1] if len(ins.operands) > 1 else None
    sdesc = ""
    if src is not None:
        if src.type == X86_OP_IMM:
            sdesc = "imm 0x%x" % src.imm
        elif src.type == X86_OP_MEM:
            sdesc = "mem disp=0x%x" % src.mem.disp
        else:
            sdesc = "reg %s" % src.reg
    print("  0x%x  %-8s %-44s <- %-18s   disp=0x%x index=%s scale=%d" %
          (ins.address, ins.mnemonic, ins.op_str, sdesc,
           dst.mem.disp, dst.mem.index, dst.mem.scale))

print()
print("=" * 78)
print("3) byte signature at the gate (file offset + VA)")
print("=" * 78)
for va, label in ((0x140264cf9, "cmp a55c,1"), (0x140264d38, "registry type4 write")):
    off = r2f(va - IB)
    print("  %-22s VA 0x%x  file 0x%x  bytes: %s" %
          (label, va, off, d[off:off + 14].hex(" ")))
