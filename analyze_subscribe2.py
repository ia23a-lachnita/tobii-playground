#!/usr/bin/env python3
"""Locate the service code paths that produce:
   "Failed to subscribe to PRP_STREAM_ENUM_%s with error %s"  (device.cpp:890)
and the 21 general_stream_subscribe wrappers, resolving RIP-relative string
references so we can see which internal stream type each wrapper requests.

Usage: python analyze_subscribe2.py [exe]
"""
import re
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

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


def cstr(rva, maxlen=160):
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


md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
md.skipdata = True

tva, tvs, trp, trs = SECS[".text"]
CODE = list(md.disasm(d[trp:trp + trs], IMAGEBASE + tva))

# index: target VA -> list of instruction addresses (rip-relative mem operands)
LEA_TARGETS = {}
for ins in CODE:
    if ins.id == 0:
        continue
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
            tgt = ins.address + ins.size + op.mem.disp
            LEA_TARGETS.setdefault(tgt, []).append(ins.address)

# index string VAs
STRINGS = {}
for m in re.finditer(rb"[\x20-\x7e]{6,}", d):
    off = m.start()
    rva = file2rva(off)
    if rva is None:
        continue
    STRINGS.setdefault(IMAGEBASE + rva, m.group().decode("ascii"))


def dump(fn_start, fn_end, label):
    fo = rva2file(fn_start - IMAGEBASE)
    if fo is None:
        return
    print("\n=== %s  fn 0x%x..0x%x (%d bytes) ===" %
          (label, fn_start, fn_end, fn_end - fn_start))
    for ins in md.disasm(d[fo:fo + fn_end - fn_start], fn_start):
        mark = ""
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            src = ins.operands[1]
            if src.type == X86_OP_MEM and src.mem.base == X86_REG_RIP:
                tgt = ins.address + ins.size + src.mem.disp
                s = STRINGS.get(tgt)
                if s:
                    mark = "   <<< %r" % s[:110]
        if ins.mnemonic == "mov" and len(ins.operands) == 2:
            dst, src = ins.operands
            if dst.type == X86_OP_MEM and src.type == X86_OP_IMM:
                mark = "   <<< imm %d (0x%x)" % (src.imm, src.imm)
        if ins.mnemonic == "call" and ins.operands and \
                ins.operands[0].type == X86_OP_IMM:
            mark = "   <<< call 0x%x" % ins.operands[0].imm
        if ins.mnemonic == "cmp" and len(ins.operands) == 2:
            dst, src = ins.operands
            if src.type == X86_OP_IMM:
                mark = "   <<< cmp imm %d" % src.imm
        print("  0x%x  %-24s %s%s" % (ins.address, ins.mnemonic,
                                       ins.op_str, mark))


NEEDLES = [
    b"Failed to subscribe to PRP_STREAM_ENUM",
    b"failed to subscribe to stream PRP_STREAM_ENUM",
    b"Found unmapped stream",
    b"Could not get tracker capabilities",
]

for needle in NEEDLES:
    print("\n########## needle: %r ##########" % needle)
    for m in re.finditer(re.escape(needle), d):
        off = m.start()
        rva = file2rva(off)
        if rva is None:
            continue
        va = IMAGEBASE + rva
        sites = LEA_TARGETS.get(va, [])
        print("  string VA 0x%x  xrefs=%s" % (va, ["0x%x" % s for s in sites]))
        done = set()
        for s in sites:
            fb = func_bounds(s)
            if fb and fb not in done:
                done.add(fb)
                dump(fb[0], fb[1], "xref fn")
