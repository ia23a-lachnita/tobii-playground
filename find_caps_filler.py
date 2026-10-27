#!/usr/bin/env python3
"""Locate the writer of the capability-flag struct at ctx+0xa4f8 (flags
0xa4f8..0xa5c0, notably 0xa55c = 'Gaze Point supported').

Strategy:
 1. Indexed stores (base+idx*4) restricted to the castor module region.
 2. memcpy/rep-movs calls whose length matches the 0xb8-byte caps struct.
 3. Any call whose argument is &ctx+0xa4f8 (LEA reg+0xa4f8) -- print the
    function's whole body so we can see how the struct gets populated.
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


STR = {}
for m in re.finditer(rb"[\x20-\x7e]{4,}", d):
    for nm, (va, vs, rp, rs) in SECS.items():
        if rp <= m.start() < rp + rs:
            STR.setdefault(IB + va + (m.start() - rp), m.group().decode())
            break

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
md.skipdata = True
tva, tvs, trp, trs = SECS[".text"]
CODE = list(md.disasm(d[trp:trp + trs], IB + tva))

# castor module region: the platform_modules/castor code
LO, HI = 0x14025f000, 0x1402e0000

print("=" * 78)
print("1) INDEXED STORES in castor region (base+idx*4) with disp<0x200")
print("=" * 78)
for ins in CODE:
    if ins.id == 0 or not ins.operands:
        continue
    if not (LO <= ins.address < HI):
        continue
    dst = ins.operands[0]
    if dst.type != X86_OP_MEM or dst.mem.index == 0:
        continue
    if ins.mnemonic not in ("mov", "or", "and", "add", "sub", "xor"):
        continue
    if dst.mem.scale not in (1, 2, 4, 8):
        continue
    print("  0x%x  %-6s %-40s idx=%s scale=%d disp=0x%x" %
          (ins.address, ins.mnemonic, ins.op_str,
           dst.mem.index, dst.mem.scale, dst.mem.disp))

print()
print("=" * 78)
print("2) memcpy-ish length immediates near castor calls (0xb8=184,0xc0,0x88,0xa8)")
print("=" * 78)
INTEREST = {0xb8, 0xc0, 0xa8, 0x88, 0xa0, 0x98, 0x70, 0x78, 0x80}
for ins in CODE:
    if ins.id == 0 or not (LO <= ins.address < HI):
        continue
    if ins.mnemonic not in ("mov", "cmp"):
        continue
    for op in ins.operands:
        if op.type == X86_OP_IMM and op.imm in INTEREST:
            print("  0x%x  %-6s %-30s imm=0x%x" %
                  (ins.address, ins.mnemonic, ins.op_str, op.imm))
            break

print()
print("=" * 78)
print("3) LEA of &ctx+0xa4f8  (+ nearby context)")
print("=" * 78)
for i, ins in enumerate(CODE):
    if ins.id == 0 or ins.mnemonic != "lea" or len(ins.operands) != 2:
        continue
    s = ins.operands[1]
    if s.type == X86_OP_MEM and s.mem.disp == 0xa4f8:
        print("\n  >>> 0x%x  %s %s" % (ins.address, ins.mnemonic, ins.op_str))
        for j in range(max(0, i - 8), min(len(CODE), i + 18)):
            x = CODE[j]
            mk = ""
            if x.mnemonic == "call" and x.operands and x.operands[0].type == X86_OP_IMM:
                mk = "   <<< call 0x%x" % x.operands[0].imm
            if x.mnemonic == "lea" and len(x.operands) == 2:
                s2 = x.operands[1]
                if s2.type == X86_OP_MEM and s2.mem.base == X86_REG_RIP:
                    st = STR.get(x.address + x.size + s2.mem.disp)
                    if st:
                        mk = "   <<< %r" % st[:70]
            print("      0x%x  %-8s %-40s%s" % (x.address, x.mnemonic, x.op_str, mk))
