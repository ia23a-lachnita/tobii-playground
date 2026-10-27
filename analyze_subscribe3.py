#!/usr/bin/env python3
"""Deep map of the service's gaze-point subscribe path.

Outputs
  A) xrefs + dump for every PRP_STREAM_ENUM_* string  -> which code names which enum
  B) xrefs + dump for "Failed to subscribe to"          -> the rejecting function
  C) full dump of general_stream_subscribe (0x140273660)
  D) full dump of the 21 thin wrappers, with the descriptor bytes they build
     (byte0 = registry selector, dword+4 = requested INTERNAL stream type)
  E) full dump of stream_type_receiver (0x140264c90)   -> registry writes

Usage: python analyze_subscribe3.py [exe] [outfile]
"""
import re
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

PATH = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
OUT = open(sys.argv[2], "w", encoding="utf-8") if len(sys.argv) > 2 else sys.stdout


def p(*a):
    print(*a, file=OUT)


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


def cstr(rva, maxlen=200):
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

RIP_TARGETS = {}
for ins in CODE:
    if ins.id == 0:
        continue
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
            tgt = ins.address + ins.size + op.mem.disp
            RIP_TARGETS.setdefault(tgt, []).append(ins.address)

STRINGS = {}
for m in re.finditer(rb"[\x20-\x7e]{5,}", d):
    off = m.start()
    rva = file2rva(off)
    if rva is None:
        continue
    STRINGS.setdefault(IMAGEBASE + rva, m.group().decode("ascii"))


def dump(fn_start, fn_end, label, only=None):
    fo = rva2file(fn_start - IMAGEBASE)
    if fo is None:
        p("  (no file mapping)")
        return
    p("")
    p("=== %s  fn 0x%x..0x%x (%d bytes) ===" %
      (label, fn_start, fn_end, fn_end - fn_start))
    for ins in md.disasm(d[fo:fo + fn_end - fn_start], fn_start):
        mark = ""
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            src = ins.operands[1]
            if src.type == X86_OP_MEM and src.mem.base == X86_REG_RIP:
                tgt = ins.address + ins.size + src.mem.disp
                s = STRINGS.get(tgt)
                if s:
                    mark = "   <<< %r" % s[:120]
        if ins.mnemonic in ("mov", "cmp", "add", "sub") and len(ins.operands) == 2:
            dst, src = ins.operands
            if dst.type == X86_OP_MEM and src.type == X86_OP_IMM:
                mark = "   <<< imm %d (0x%x)" % (src.imm, src.imm)
            elif src.type == X86_OP_IMM and dst.type != X86_OP_MEM:
                mark = "   <<< imm %d (0x%x)" % (src.imm, src.imm)
        if ins.mnemonic == "call" and ins.operands and \
                ins.operands[0].type == X86_OP_IMM:
            mark = "   <<< call 0x%x" % ins.operands[0].imm
        if only and only not in ins.mnemonic:
            continue
        p("  0x%x  %-24s %s%s" % (ins.address, ins.mnemonic, ins.op_str, mark))


# ---------------------------------------------------------------- A) PRP enum strings
p("################ A) PRP_STREAM_ENUM_* string xrefs ################")
for m in re.finditer(rb"PRP_STREAM_ENUM_[A-Z0-9_]+", d):
    off = m.start()
    rva = file2rva(off)
    if rva is None:
        continue
    va = IMAGEBASE + rva
    sites = RIP_TARGETS.get(va, [])
    p("  %-52s VA 0x%x  xref=%s" %
      (m.group().decode(), va, ["0x%x" % s for s in sites]))

# ---------------------------------------------------------------- B) subscribe reject
p("")
p("################ B) 'subscribe' related strings ################")
for needle in (b"Failed to subscribe", b"failed to subscribe to stream",
               b"PLATMOD_ERROR_NOT_SUPPORTED", b"NOT_SUPPORTED"):
    for m in re.finditer(re.escape(needle), d):
        off = m.start()
        rva = file2rva(off)
        if rva is None:
            continue
        va = IMAGEBASE + rva
        p("  %-32r VA 0x%x xref=%s" %
          (needle, va, ["0x%x" % s for s in RIP_TARGETS.get(va, [])]))

# ---------------------------------------------------------------- C) subscribe fn
p("")
p("################ C) general_stream_subscribe ################")
fb = func_bounds(0x140273660)
dump(fb[0], fb[1], "general_stream_subscribe")

# ---------------------------------------------------------------- D) wrappers
WRAPPERS = [0x140274ae0, 0x140274ca0, 0x140274e50, 0x140275000, 0x1402751a0,
            0x140275360, 0x140275520, 0x140275e10, 0x140275fc0, 0x140276170,
            0x140276330, 0x1402764f0, 0x140276700, 0x1402768b0, 0x140276a60,
            0x140276c20, 0x140276dd0, 0x1402770b0, 0x140277260, 0x140277410,
            0x1402777e0]
p("")
p("################ D) the 21 subscribe wrappers ################")
for w in WRAPPERS:
    fb = func_bounds(w)
    if not fb:
        p("  wrapper 0x%x: no bounds" % w)
        continue
    p("")
    p("---- wrapper 0x%x  fn 0x%x..0x%x ----" % (w, fb[0], fb[1]))
    fo = rva2file(fb[0] - IMAGEBASE)
    for ins in md.disasm(d[fo:fo + fb[1] - fb[0]], fb[0]):
        mark = ""
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            src = ins.operands[1]
            if src.type == X86_OP_MEM and src.mem.base == X86_REG_RIP:
                s = STRINGS.get(ins.address + ins.size + src.mem.disp)
                if s:
                    mark = "   <<< %r" % s[:120]
        if ins.mnemonic in ("mov", "cmp", "add", "sub") and len(ins.operands) == 2:
            dst, src = ins.operands
            if src.type == X86_OP_IMM:
                mark = "   <<< imm %d (0x%x)" % (src.imm, src.imm)
        if ins.mnemonic == "call" and ins.operands and \
                ins.operands[0].type == X86_OP_IMM:
            mark = "   <<< call 0x%x" % ins.operands[0].imm
        p("  0x%x  %-24s %s%s" % (ins.address, ins.mnemonic, ins.op_str, mark))

# ---------------------------------------------------------------- E) stream_type_receiver
p("")
p("################ E) stream_type_receiver ################")
fb = func_bounds(0x140264c90)
dump(fb[0], fb[1], "stream_type_receiver")
OUT.close()
print("written")
