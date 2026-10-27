#!/usr/bin/env python3
"""Find every read/write of the castor capability flags that gate the
publication of internal stream types into registry A.

  ctx+0xa558 -> gates internal type 0x21 (Absolute Eye Openness)
  ctx+0xa55c -> gates internal type 4    (Gaze Point)      <-- GAZE POINT
  ctx+0xa560 -> gates internal type 0x1d (Responsive Gaze Point)

File mapping: rva = file + 0xc00 ; VA = 0x140000000 + rva
"""
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM

PATH = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
FLAGS = [0xA558, 0xA55C, 0xA560, 0xA5A8, 0xA5B0, 0xA590, 0xA5AC]
TEXT_VA = 0x140001000
TEXT_FILE = 0x400
TEXT_SIZE = 0x260000

d = open(PATH, "rb").read()
code = d[TEXT_FILE:TEXT_FILE + TEXT_SIZE]
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True

hits = {}
for ins in md.disasm(code, TEXT_VA):
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.disp in FLAGS:
            hits.setdefault(op.mem.disp, []).append((ins.address, ins.mnemonic,
                                                     ins.op_str))

for f in FLAGS:
    lst = hits.get(f, [])
    print("=== ctx+0x%x : %d references ===" % (f, len(lst)))
    for a, m, o in lst:
        print("   0x%x  %-8s %s" % (a, m, o))
    print()
