#!/usr/bin/env python3
"""Find the writer of ctx+0xa55c.

Hypothesis: ctx+0xa4f8 is a device-info/capability FLAG STRUCT. The flag at
+0x64 (0xa55c) has no direct `mov [reg+disp],imm` writer, so it is filled by a
block copy or an indexed store. Find:
  A. every .text store that uses an INDEX register (base+idx*4) -- then check
     whether the base was loaded from ctx+0xa4f8 in the same function.
  B. all functions that take &ctx+0xa4f8 as a destination argument.
  C. dump FUN_140265360 (called with rdx = ctx+0xa4f8 from FUN_140263a90).
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
                mk += "  disp=0x%x idx=%s" % (s.mem.disp, s.mem.index)
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            mk = "   <<< call 0x%x" % ins.operands[0].imm
        if ins.mnemonic.startswith("j") and ins.operands and ins.operands[0].type == X86_OP_IMM:
            mk = "   <<< -> 0x%x" % ins.operands[0].imm
        print("  0x%x  %-18s %-42s%s" % (ins.address, ins.mnemonic, ins.op_str, mk))


print("=" * 78)
print("A) INDEXED STORES in .text (base + idx*scale) -- candidates for a55c fill")
print("=" * 78)
for ins in CODE:
    if ins.id == 0 or not ins.operands:
        continue
    dst = ins.operands[0]
    if dst.type != X86_OP_MEM or dst.mem.index == 0:
        continue
    if ins.mnemonic not in ("mov", "or", "and", "add", "sub", "xor"):
        continue
    fb = fbnd(ins.address)
    print("  0x%x  %-6s %-40s idx=%s scale=%d disp=0x%x   fn %s" %
          (ins.address, ins.mnemonic, ins.op_str,
           ins.operands[0].mem.index, ins.operands[0].mem.scale,
           ins.operands[0].mem.disp,
           ("0x%x..0x%x" % fb) if fb else "?"))

print()
print("=" * 78)
print("B) FUNCTIONS referencing &ctx+0xa4f8 (LEA base+0xa4f8)")
print("=" * 78)
for ins in CODE:
    if ins.id == 0 or ins.mnemonic != "lea" or len(ins.operands) != 2:
        continue
    s = ins.operands[1]
    if s.type == X86_OP_MEM and s.mem.disp == 0xa4f8:
        fb = fbnd(ins.address)
        print("  0x%x  lea %-34s   fn %s" %
              (ins.address, ins.op_str, ("0x%x..0x%x" % fb) if fb else "?"))

print()
print("=" * 78)
print("C) FUN_140265360  (called with rdx = ctx+0xa4f8)")
print("=" * 78)
fb = fbnd(0x140265360)
print("  pdata bounds: %s" % (("0x%x..0x%x" % fb) if fb else "not in .pdata"))
if fb:
    show(fb[0], fb[1], "FUN_140265360 full")
else:
    show(0x140265360, 0x140265360 + 0x300, "FUN_140265360 (guess window)")
