#!/usr/bin/env python3
"""Full-section scan for reads/writes of the castor capability flags.

The earlier scan_cap_flags.py used TEXT_SIZE=0x260000 and therefore missed
the whole stream_type_receiver region (file 0x2630xx+).  This version derives
the .text bounds from the PE section table and scans the WHOLE section.

Flags of interest (castor ctx):
  ctx+0xa558 -> gates internal type 0x21 (Absolute Eye Openness)
  ctx+0xa55c -> gates internal type 4    (Gaze Point)      <-- GAZE POINT
  ctx+0xa560 -> gates internal type 0x1d (Responsive Gaze Point)
  ctx+0xa5b0 -> device-info-present flag (gates the custom stream entry)
  ctx+0xae34 -> platform classifier (0 = desktop flat display)
  ctx+0xa5a8, 0xa5ac, 0xa590, 0xa59c, 0xa594, 0xa598

Usage: python scan_cap_flags2.py [path-to-exe]
"""
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_MEM

PATH = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
FLAGS = [0xA558, 0xA55C, 0xA560, 0xA5A8, 0xA5AC, 0xA5B0, 0xA590, 0xA59C,
         0xA594, 0xA598, 0xAE34, 0xA5A0, 0xA58C]
IMAGEBASE = 0x140000000

d = open(PATH, "rb").read()

e = struct.unpack("<I", d[0x3C:0x40])[0]
coff = e + 4
nsec = struct.unpack("<H", d[coff + 2:coff + 4])[0]
so = coff + 20 + struct.unpack("<H", d[coff + 16:coff + 18])[0]

text = None
for i in range(nsec):
    s = so + i * 40
    nm = d[s:s + 8].rstrip(b"\x00").decode("latin1")
    vs, va, rs, rp = struct.unpack("<IIII", d[s + 8:s + 24])
    print("section %-9s va=0x%08x vs=0x%08x rp=0x%08x rs=0x%08x"
          % (nm, va, vs, rp, rs))
    if nm.startswith(".text"):
        text = (va, vs, rp, rs)

if text is None:
    raise SystemExit("[!] no .text section")

tva, tvs, trp, trs = text
code = d[trp:trp + trs]
print("\n.text: file 0x%x..0x%x  va 0x%x..0x%x" %
      (trp, trp + trs, IMAGEBASE + tva, IMAGEBASE + tva + tvs))

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
md.skipdata = True       # do not stop at the first invalid byte in .text

hits = {}
for ins in md.disasm(code, IMAGEBASE + tva):
    if ins.id == 0:            # skipdata pseudo-instruction
        continue
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.disp in FLAGS:
            hits.setdefault(op.mem.disp, []).append(
                (ins.address, ins.mnemonic, ins.op_str))

for f in FLAGS:
    lst = hits.get(f, [])
    print("\n=== ctx+0x%x : %d references ===" % (f, len(lst)))
    for a, m, o in lst:
        print("   VA 0x%x  file 0x%08x  %-8s %s"
              % (a, a - IMAGEBASE - tva + trp, m, o))
