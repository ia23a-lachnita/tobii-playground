#!/usr/bin/env python3
"""Map PRP_STREAM_ENUM_* names to their enum values, and find the function that
translates a PRP stream enum into an internal castor stream type.

Steps
  1. collect every PRP_STREAM_ENUM_* string and its VA
  2. find 8-byte little-endian pointers to those VAs  -> the name table
  3. the table index == enum value
  4. find code referencing the table (rip-relative) -> the translator
  5. dump the translator's disassembly with strings and immediates resolved

Usage: python analyze_prp_map.py [exe]
"""
import re
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM

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


# --- .pdata --------------------------------------------------------------
pva, pvs, prp, prs = SECS[".pdata"]
FUNCS = sorted((IMAGEBASE + b, IMAGEBASE + en) for b, en, _ in
               (struct.unpack("<III", d[prp + i * 12:prp + i * 12 + 12])
                for i in range(pvs // 12)))


def func_bounds(va):
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


# --- PRP enum strings ----------------------------------------------------
names = {}
for m in re.finditer(rb"PRP_STREAM_ENUM_[A-Z0-9_]+", d):
    rva = file2rva(m.start())
    if rva is None:
        continue
    names[IMAGEBASE + rva] = m.group().decode()

print("== PRP stream enum name strings ==")
for va in sorted(names):
    print("   VA 0x%x  %s" % (va, names[va]))

# --- pointers to them ----------------------------------------------------
ptrs = {}
for va in names:
    pat = struct.pack("<Q", va)
    start = 0
    while True:
        i = d.find(pat, start)
        if i < 0:
            break
        start = i + 1
        rva = file2rva(i)
        if rva is not None:
            ptrs.setdefault(IMAGEBASE + rva, []).append(names[va])

print("\n== pointer tables ==")
for tbl, lst in sorted(ptrs.items()):
    print("   table VA 0x%x  (%d entries)" % (tbl, len(lst)))
    # index = (entry VA - tbl VA)/8
    for k in range(len(lst)):
        print("        [%2d] = %s" % (k, lst[k]))

# --- code referencing the tables ----------------------------------------
tva, tvs, trp, trs = SECS[".text"]
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
md.skipdata = True

refs = {}
for ins in md.disasm(d[trp:trp + trs], IMAGEBASE + tva):
    if ins.id == 0:
        continue
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.base == 0 and op.mem.disp:
            tgt = op.mem.disp
            if tgt in ptrs:
                refs.setdefault(tgt, []).append(ins.address)

print("\n== code referencing the name tables ==")
for tbl, sites in sorted(refs.items()):
    print("   table 0x%x referenced from:" % tbl)
    for s in sites:
        fb = func_bounds(s)
        print("       0x%x  fn %s" % (s, ("0x%x..0x%x" % fb) if fb else "?"))

# --- dump the biggest referencing function ------------------------------
if refs:
    best = max(refs.items(), key=lambda kv: len(kv[1]))
    tbl = best[0]
    sites = best[1]
    fb = func_bounds(sites[0])
    if fb:
        print("\n== dump fn 0x%x..0x%x (references table 0x%x) ==" %
              (fb[0], fb[1], tbl))
        fo = rva2file(fb[0] - IMAGEBASE)
        for ins in md.disasm(d[fo:fo + fb[1] - fb[0]], fb[0]):
            mark = ""
            if ins.mnemonic == "lea" and len(ins.operands) == 2:
                src = ins.operands[1]
                if src.type == X86_OP_MEM and src.mem.base == 0 and src.mem.disp:
                    st = cstr(src.mem.disp - IMAGEBASE)
                    if st:
                        mark = "   <<< %r" % st[:70]
                    elif src.mem.disp in ptrs:
                        mark = "   <<< TABLE 0x%x" % src.mem.disp
            if ins.mnemonic == "mov" and len(ins.operands) == 2:
                dst, src = ins.operands
                if dst.type == X86_OP_MEM and src.type == X86_OP_IMM:
                    if src.imm <= 0x80:
                        mark = "   <<< imm %d (0x%x)" % (src.imm, src.imm)
            if ins.mnemonic == "call" and ins.operands and \
                    ins.operands[0].type == X86_OP_IMM:
                mark = "   <<< call 0x%x" % ins.operands[0].imm
            print("  0x%x  %-26s %s%s" % (ins.address, ins.mnemonic,
                                           ins.op_str, mark))
