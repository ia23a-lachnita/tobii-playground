#!/usr/bin/env python3
"""Local (no-MCP) analysis of the platform runtime service:

 1. parse .pdata to get exact function bounds for any VA (RUNTIME_FUNCTION)
 2. index every RIP-relative LEA in .text -> target VA
 3. map each general_stream_subscribe call site to:
      - its containing function
      - the ASCII strings that function references
      - the small immediate stores it performs before the call
 4. locate the xref of a given string and dump that function's disassembly

Usage:
  python analyze_subscribe_map.py [exe]                # table of all 21 wrappers
  python analyze_subscribe_map.py [exe] --xref <needle>  # dump fn referencing needle
"""
import re
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM

PATH = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
IMAGEBASE = 0x140000000
TEXT_VA = 0x140001000
TEXT_FILE = 0x400
TEXT_SIZE = 0x43C400
TARGET = 0x140273660

CALLERS = [0x140274ae0, 0x140274ca0, 0x140274e50, 0x140275000, 0x1402751a0,
           0x140275360, 0x140275520, 0x140275e10, 0x140275fc0, 0x140276170,
           0x140276330, 0x1402764f0, 0x140276700, 0x1402768b0, 0x140276a60,
           0x140276c20, 0x140276dd0, 0x1402770b0, 0x140277260, 0x140277410,
           0x1402777e0]

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


def cstr(rva, maxlen=120):
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


# ---- .pdata -> function bounds -------------------------------------------
pva, pvs, prp, prs = SECS[".pdata"]
FUNCS = []
for i in range(pvs // 12):
    b, en, _u = struct.unpack("<III", d[prp + i * 12:prp + i * 12 + 12])
    FUNCS.append((IMAGEBASE + b, IMAGEBASE + en))
FUNCS.sort()


def func_bounds(va):
    lo, hi = 0, len(FUNCS) - 1
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        s, e2 = FUNCS[mid]
        if va < s:
            hi = mid - 1
        elif va >= e2:
            lo = mid + 1
        else:
            return (s, e2)
    return best


# ---- RIP-relative LEA index ---------------------------------------------
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
md.skipdata = True

code = d[TEXT_FILE:TEXT_FILE + TEXT_SIZE]
LEAX = {}
STORES = {}
for ins in md.disasm(code, TEXT_VA):
    if ins.id == 0:
        continue
    if ins.mnemonic == "lea" and len(ins.operands) == 2:
        dst, src = ins.operands
        if src.type == X86_OP_MEM and src.mem.base == 0 and src.mem.disp:
            LEAX.setdefault(src.mem.disp, []).append(ins.address)
    if ins.mnemonic == "mov" and len(ins.operands) == 2:
        dst, src = ins.operands
        if dst.type == X86_OP_MEM and src.type == X86_OP_IMM and src.imm <= 0x400:
            STORES.setdefault(ins.address, (ins.mnemonic, ins.op_str, src.imm))


def fn_strings(start, end):
    out = []
    for site, targets in LEAX.items():
        pass
    return out


def strings_in(fn_start, fn_end):
    res = []
    for tgt, sites in LEAX.items():
        for s in sites:
            if fn_start <= s < fn_end:
                st = cstr(tgt - IMAGEBASE)
                if st:
                    res.append((s, st))
                break
    return sorted(res)


def disasm_fn(fn_start, fn_end):
    fo = rva2file(fn_start - IMAGEBASE)
    n = fn_end - fn_start
    return list(md.disasm(d[fo:fo + n], fn_start))


if "--xref" in sys.argv:
    needle = sys.argv[sys.argv.index("--xref") + 1]
    hits = []
    for m in re.finditer(re.escape(needle.encode()), d):
        off = m.start()
        rva = file2rva(off)
        if rva is None:
            continue
        tgt = IMAGEBASE + rva
        for s in LEAX.get(tgt, []):
            fb = func_bounds(s)
            hits.append((s, fb, tgt))
    for s, fb, tgt in sorted(set(hits)):
        print("xref site 0x%x -> fn %s  (str VA 0x%x)" %
              (s, ("0x%x..0x%x" % fb) if fb else "?", tgt))
        if fb:
            for ins in disasm_fn(*fb):
                mark = ""
                if ins.mnemonic == "call" and ins.operands and \
                        ins.operands[0].type == X86_OP_IMM:
                    mark = "   <<< call 0x%x" % ins.operands[0].imm
                if ins.mnemonic == "mov" and len(ins.operands) == 2:
                    dst, src = ins.operands
                    if dst.type == X86_OP_MEM and src.type == X86_OP_IMM:
                        mark = "   <<< store imm %d" % src.imm
                if ins.mnemonic == "lea" and len(ins.operands) == 2:
                    dst, src = ins.operands
                    if src.type == X86_OP_MEM and src.mem.base == 0 and src.mem.disp:
                        st = cstr(src.mem.disp - IMAGEBASE)
                        if st:
                            mark = "   <<< %r" % st[:70]
                print("  0x%x  %-26s %s%s" % (ins.address, ins.mnemonic,
                                               ins.op_str, mark))
    sys.exit(0)

print("== general_stream_subscribe wrappers ==")
for c in CALLERS:
    fb = func_bounds(c)
    if not fb:
        print("\ncall 0x%x  <no .pdata bounds>" % c)
        continue
    ss = strings_in(*fb)
    print("\ncall 0x%x  fn 0x%x..0x%x  (%d bytes)" % (c, fb[0], fb[1], fb[1] - fb[0]))
    for s, st in ss:
        print("    str 0x%x  %r" % (s, st[:78]))
