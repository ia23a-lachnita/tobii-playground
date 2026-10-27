#!/usr/bin/env python3
"""Find the writer of ctx+0xa55c.

ctx+0xa4f8 is a 0xb8-byte capability-flag struct (0xa4f8..0xa5b0).
a55c = base + 0x64, a560 = base + 0x68, a558 = base + 0x60.
So the writer probably stores at [ctx+0xa4f8 + 0x64] i.e. disp 0x64 with the
base already in a register. Scan the castor module for stores with small
displacements (0x00..0xb8) and report their function + context.
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


LO, HI = 0x14025f000, 0x1402e0000
TARGETS = {0x60: "a558", 0x64: "a55c<GazePoint>", 0x68: "a560<ResponsiveGazePoint>"}

print("=" * 78)
print("STORES with disp 0x60/0x64/0x68 in the castor module (0x14025f000..0x1402e0000)")
print("=" * 78)
hits = []
for ins in CODE:
    if ins.id == 0 or not ins.operands:
        continue
    if not (LO <= ins.address < HI):
        continue
    dst = ins.operands[0]
    if dst.type != X86_OP_MEM or dst.mem.index != 0:
        continue
    if ins.mnemonic not in ("mov", "or", "and", "add", "sub", "xor"):
        continue
    if dst.mem.disp in TARGETS:
        hits.append(ins)

for ins in hits:
    src = ins.operands[1] if len(ins.operands) > 1 else None
    sd = ""
    if src is not None:
        if src.type == X86_OP_IMM:
            sd = "imm 0x%x" % src.imm
        elif src.type == X86_OP_REG:
            sd = "reg"
        else:
            sd = "mem"
    fb = fbnd(ins.address)
    print("\n  >>> 0x%x  %-6s %-34s <- %-10s   [%s]  fn %s" %
          (ins.address, ins.mnemonic, ins.op_str, sd,
           TARGETS[ins.operands[0].mem.disp],
           ("0x%x..0x%x" % fb) if fb else "?"))
    if fb:
        idx = next((i for i, x in enumerate(CODE)
                    if x.address == ins.address), None)
        if idx is not None:
            for x in CODE[max(0, idx - 14):idx + 6]:
                mk = ""
                if x.mnemonic == "lea" and len(x.operands) == 2:
                    s2 = x.operands[1]
                    if s2.type == X86_OP_MEM and s2.mem.base == X86_REG_RIP:
                        st = STR.get(x.address + x.size + s2.mem.disp)
                        if st:
                            mk = "   <<< %r" % st[:70]
                if x.mnemonic == "call" and x.operands and x.operands[0].type == X86_OP_IMM:
                    mk = "   <<< call 0x%x" % x.operands[0].imm
                print("      0x%x  %-8s %-38s%s" % (x.address, x.mnemonic, x.op_str, mk))
