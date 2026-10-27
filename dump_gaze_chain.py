#!/usr/bin/env python3
"""Targeted dumps for the gaze-point subscribe chain (compact output).

  1) stream_type_receiver 0x14026501e..0x140265360  (the id-5 / id-0 handler)
  2) every wrapper's descriptor: selector byte + requested INTERNAL type
  3) general_stream_subscribe registry lookup (0x140273660..)

Usage: python dump_gaze_chain.py [exe]
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


def cstr(rva, n=200):
    o = r2f(rva)
    if o is None:
        return None
    end = d.find(b"\x00", o, o + n)
    if end < 0:
        return None
    raw = d[o:end]
    try:
        s = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    return s if all(32 <= ord(c) < 127 for c in s) else None


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


md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
md.skipdata = True

STR = {}
for m in re.finditer(rb"[\x20-\x7e]{4,}", d):
    r = f2r(m.start())
    if r is not None:
        STR.setdefault(IB + r, m.group().decode())


def disasm(a, b):
    o = r2f(a - IB)
    if o is None:
        return []
    return list(md.disasm(d[o:o + b - a], a))


def show(ins_list, tag_filter=None):
    for ins in ins_list:
        mark = ""
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            src = ins.operands[1]
            if src.type == X86_OP_MEM and src.mem.base == X86_REG_RIP:
                s = STR.get(ins.address + ins.size + src.mem.disp)
                if s:
                    mark = "   <<< %r" % s[:100]
        if ins.mnemonic in ("mov", "cmp", "add", "sub") and len(ins.operands) == 2:
            dst, src = ins.operands
            if src.type == X86_OP_IMM:
                mark = "   <<< imm %d (0x%x)" % (src.imm, src.imm)
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            mark = "   <<< call 0x%x" % ins.operands[0].imm
        line = "  0x%x  %-22s %s%s" % (ins.address, ins.mnemonic, ins.op_str, mark)
        if tag_filter and tag_filter not in line:
            continue
        print(line)


print("################ 1) id-5/id-0 handler in stream_type_receiver ################")
show(disasm(0x14026501e, 0x140265360))

print()
print("################ 2) general_stream_subscribe (registry lookup) ################")
b = fbnd(0x140273660)
show(disasm(b[0], b[1]))

print()
print("################ 3) wrapper descriptors ################")
WRAPPERS = [0x140274ae0, 0x140274ca0, 0x140274e50, 0x140275000, 0x1402751a0,
            0x140275360, 0x140275520, 0x140275e10, 0x140275fc0, 0x140276170,
            0x140276330, 0x1402764f0, 0x140276700, 0x1402768b0, 0x140276a60,
            0x140276c20, 0x140276dd0, 0x1402770b0, 0x140277260, 0x140277410,
            0x1402777e0]
for w in WRAPPERS:
    fb = fbnd(w)
    ins_list = disasm(fb[0], fb[1])
    call_i = None
    for i, ins in enumerate(ins_list):
        if ins.mnemonic == "call" and ins.operands and \
                ins.operands[0].type == X86_OP_IMM and ins.operands[0].imm == 0x140273660:
            call_i = i
            break
    print("\n--- wrapper 0x%x (fn 0x%x..0x%x) ---" % (w, fb[0], fb[1]))
    if call_i is None:
        # some wrappers call a different subscribe entry
        for i, ins in enumerate(ins_list):
            if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
                print("   calls 0x%x" % ins.operands[0].imm)
        continue
    for ins in ins_list[max(0, call_i - 18):call_i + 1]:
        mark = ""
        if ins.mnemonic in ("mov", "cmp", "add", "sub") and len(ins.operands) == 2:
            dst, src = ins.operands
            if src.type == X86_OP_IMM:
                mark = "   <<< imm %d (0x%x)" % (src.imm, src.imm)
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            mark = "   <<< call 0x%x" % ins.operands[0].imm
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            src = ins.operands[1]
            if src.type == X86_OP_MEM and src.mem.base == X86_REG_RIP:
                s = STR.get(ins.address + ins.size + src.mem.disp)
                if s:
                    mark = "   <<< %r" % s[:100]
        print("   0x%x  %-22s %s%s" % (ins.address, ins.mnemonic, ins.op_str, mark))
