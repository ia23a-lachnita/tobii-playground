#!/usr/bin/env python3
"""Find the writer(s) of the castor capability flag ctx+0xa55c.

Raw disp32 scan (no capstone, so no desync risk):
  [rbx+0xa55c] -> bytes 5c a5 00 00
  [rcx+0xa55c] -> same disp; the register is in the preceding ModRM byte.
Print every hit with 12 bytes of context so the instruction can be read
by eye.

File mapping: rva = file + 0xc00 ; VA = 0x140000000 + rva
"""
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
d = open(PATH, "rb").read()

for name, disp in (("0xa55c (Gaze Point gate)", bytes.fromhex("5ca50000")),
                   ("0xa560 (Responsive Gaze Point)", bytes.fromhex("60a50000")),
                   ("0xa558 (Absolute Eye Openness)", bytes.fromhex("58a50000"))):
    hits = []
    i = 0
    while True:
        i = d.find(disp, i)
        if i < 0:
            break
        hits.append(i)
        i += 1
    print("=== %s : %d hits ===" % (name, len(hits)))
    for h in hits:
        va = 0x140000000 + h + 0xC00
        ctx = d[max(0, h - 6):h + 12]
        print("   file 0x%08x  VA 0x%x   ctx: %s" % (h, va, ctx.hex(" ")))
    print()

print("=== current bytes at the proposed patch site ===")
SITE = 0x264100
print("   file 0x%x : %s" % (SITE, d[SITE:SITE + 12].hex(" ")))
print("   file 0x%x (cmp opcode) : %s" % (SITE - 7, d[SITE - 7:SITE + 6].hex(" ")))
