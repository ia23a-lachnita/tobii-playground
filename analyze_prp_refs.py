#!/usr/bin/env python3
"""Find functions that reference PRP_STREAM_ENUM_* string addresses."""
import re
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_MEM

PATH = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
IMAGEBASE = 0x140000000

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

def rva2file(rva):
    for nm, (va, vs, rp, rs) in SECS.items():
        if va <= rva < va + max(vs, rs):
            return rp + (rva - va)
    return None

def file2rva(off):
    for nm, (va, vs, rp, rs) in SECS.items():
        if rp <= off < rp + rs:
            return va + (off - rp)
    return None

def cstr(rva, maxlen=100):
    off = rva2file(rva)
    if off is None:
        return None
    end = d.find(b"\x00", off, off + maxlen)
    if end < 0:
        return None
    raw = d[off:end]
    if not raw:
        return None
    try:
        s = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    return s if all(32 <= ord(c) < 127 for c in s) else None

pva, pvs, prp, prs = SECS[".pdata"]
FUNCS = sorted(
    (IMAGEBASE + b, IMAGEBASE + en)
    for b, en, _ in (
        struct.unpack("<III", d[prp + i * 12:prp + i * 12 + 12])
        for i in range(pvs // 12)
    )
)

def func_bounds(va):
    lo, hi = 0, len(FUNCS) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        s, en = FUNCS[mid]
        if va < s:
            hi = mid - 1
        elif va >= en:
            lo = mid + 1
        else:
            return (s, en)
    return None

names = {}
for m in re.finditer(rb"PRP_STREAM_ENUM_[A-Z0-9_]+", d):
    rva = file2rva(m.start())
    if rva is None:
        continue
    names[IMAGEBASE + rva] = m.group().decode()

targets = set(names)
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
md.skipdata = True
text_va, text_vs, text_rp, text_rs = SECS[".text"]
refs = {}
for ins in md.disasm(d[text_rp:text_rp + text_rs], IMAGEBASE + text_va):
    if ins.id == 0:
        continue
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.base == 0 and op.mem.disp:
            if op.mem.disp in targets:
                fb = func_bounds(ins.address)
                refs.setdefault(ins.address, (op.mem.disp, fb))

print("== direct RIP-relative references to PRP enum strings ==")
for site, (target, fb) in sorted(refs.items()):
    print("  0x%x -> 0x%x  fn %s" % (site, target, ("0x%x..0x%x" % fb) if fb else "?"))

print("\n== referencing functions ==")
groups = {}
for site, (target, fb) in refs.items():
    if fb:
        groups.setdefault(fb[0], []).append((site, target))
for start, lst in sorted(groups.items()):
    end = func_bounds(start)
    size = end[1] - start if end else 0
    print("FN 0x%x..0x%x size=%d sites=%d" % (start, end[1] if end else start + size, size, len(lst)))
    for site, target in sorted(lst):
        print("   0x%x -> 0x%x" % (site, target))

if groups:
    start = max(groups, key=lambda s: len(groups[s]))
    end = func_bounds(start)
    size = end[1] - start if end else 0
    print("\n== dump biggest referencing function 0x%x..0x%x ==" % (start, end[1] if end else start + size))
    fo = rva2file(start - IMAGEBASE)
    for ins in md.disasm(d[fo:fo + size], start):
        mark = ""
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            src = ins.operands[1]
            if src.type == X86_OP_MEM and src.mem.base == 0 and src.mem.disp:
                st = cstr(src.mem.disp - IMAGEBASE)
                if st:
                    mark = "   <<< %r" % st[:70]
                elif src.mem.disp in targets:
                    mark = "   <<< TABLE 0x%x" % src.mem.disp
        if ins.mnemonic == "mov" and len(ins.operands) == 2:
            dst, src = ins.operands
            if dst.type == X86_OP_MEM and src.type == X86_OP_IMM:
                if src.imm <= 0x80:
                    mark = "   <<< imm %d (0x%x)" % (src.imm, src.imm)
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            mark = "   <<< call 0x%x" % ins.operands[0].imm
        print("  0x%x  %-26s %s%s" % (ins.address, ins.mnemonic, ins.op_str, mark))
