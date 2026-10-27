#!/usr/bin/env python3
"""Map the stream_type_receiver dispatch ladder (FUN_140264c90) id->handler.

Prints, for each `cmp eax, IMM` in the ladder, the comparison VA, the id, the
branch target, and the first instruction of the handler block it falls into.
Then lists which capability-flag reads (ctx+0xa4f8..0xa5c0) live in which
handler block, so we can tell WHICH device-announced stream id owns the
a55c ('Gaze Point' internal type 4) check.
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

START, END = 0x140264c90, 0x140265360
off = r2f(START - IB)
INS = list(md.disasm(d[off:off + (END - START)], START))

# Collect ladder entries: cmp eax, IMM ; jne TARGET
ladder = []
for i, ins in enumerate(INS):
    if (ins.mnemonic == "cmp" and len(ins.operands) == 2
            and ins.operands[0].type == 1 and ins.operands[1].type == X86_OP_IMM):
        imm = ins.operands[1].imm
        nxt = INS[i + 1] if i + 1 < len(INS) else None
        if nxt and nxt.mnemonic.startswith("j") and nxt.operands and nxt.operands[0].type == X86_OP_IMM:
            ladder.append((ins.address, imm, nxt.operands[0].imm, nxt.mnemonic))

print("=" * 78)
print("LADDER in FUN_140264c90 (stream_type_receiver)")
print("=" * 78)
for va, imm, tgt, jm in ladder:
    print("  cmp eax,0x%-4x  at 0x%x   %-4s -> 0x%x" % (imm, va, jm, tgt))

print()
print("=" * 78)
print("FLAG READS in the function, grouped by owning ladder block")
print("=" * 78)
FLAG = {0xa4f8: "a4f8", 0xa4fc: "a4fc", 0xa504: "a504", 0xa508: "a508",
        0xa510: "a510", 0xa518: "a518", 0xa51c: "a51c", 0xa55c: "a55c<GazePoint>",
        0xa558: "a558", 0xa560: "a560<ResponsiveGazePoint>", 0xa568: "a568",
        0xa56c: "a56c", 0xa570: "a570", 0xa574: "a574", 0xa578: "a578",
        0xa57c: "a57c", 0xa580: "a580", 0xa584: "a584", 0xa588: "a588",
        0xa590: "a590<HeadPose>", 0xa594: "a594", 0xa598: "a598",
        0xa59c: "a59c", 0xa5a0: "a5a0", 0xa5a4: "a5a4", 0xa5a8: "a5a8",
        0xa5ac: "a5ac", 0xa5b0: "a5b0<deviceInfo>", 0xae34: "ae34<platformBucket>"}

# For each instruction, find which cmp block it belongs to: the last ladder cmp
# whose "fall-through" region contains it. Fall-through region of cmp at va
# with jne->tgt = (va_after_cmp .. tgt) when tgt > va (next test), else it's
# the "else chain". Simpler: print each flag read with the nearest preceding
# ladder cmp and note the direction.
blocks = []
for va, imm, tgt, jm in ladder:
    blocks.append((va, imm, tgt))
for i, ins in enumerate(INS):
    if ins.id == 0:
        continue
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.disp in FLAG:
            prev = None
            for va, imm, tgt in blocks:
                if va < ins.address:
                    prev = (va, imm, tgt)
            print("  0x%x  %-8s %-30s   flag=%-24s  last-cmp id=0x%x @0x%x" %
                  (ins.address, ins.mnemonic, ins.op_str,
                   FLAG[op.mem.disp], prev[1] if prev else -1,
                   prev[0] if prev else 0))
            break
