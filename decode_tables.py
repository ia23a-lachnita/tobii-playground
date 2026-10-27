#!/usr/bin/env python3
"""Decode:
  (A) internal stream type -> descriptor name, from the switch inside
      helper 0x140277c20 (byte table 0x140278124 + dword jump table 0x1402780e4)
  (B) PRP stream enum -> wrapper VA, from the switch in device::subscribe
      (dword jump table 0x1400f86e4, base = module base)
  (C) for each wrapper: which helper + which internal type + which selector byte
      it passes, i.e. the descriptor it builds for general_stream_subscribe
  (D) every write into registry A (ctx+0x10e8, count ctx+0x14e8) and registry B
      (ctx+0x18f0?) in stream_type_receiver, with the stream id that triggers it

Usage: python decode_tables.py [exe]
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

PRP_NAMES = {}
for m in re.finditer(rb"PRP_STREAM_ENUM_[A-Z0-9_]+", d):
    r = f2r(m.start())
    if r is not None:
        PRP_NAMES[IB + r] = m.group().decode()


def disasm(a, b):
    o = r2f(a - IB)
    if o is None:
        return []
    return list(md.disasm(d[o:o + b - a], a))


def name_at(tgt):
    """first string referenced by the code block at tgt"""
    for ins in disasm(tgt, tgt + 0x40):
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            src = ins.operands[1]
            if src.type == X86_OP_MEM and src.mem.base == X86_REG_RIP:
                va = ins.address + ins.size + src.mem.disp
                s = STR.get(va)
                if s:
                    return s
    return None


print("== (A) internal stream type -> descriptor name (helper 0x140277c20) ==")
BYTE_TBL = IB + 0x278124
JMP_TBL = IB + 0x2780e4
for t in range(0, 0x22):
    g = d[r2f(BYTE_TBL - IB) + t]
    off = struct.unpack("<i", d[r2f(JMP_TBL - IB) + 4 * g:r2f(JMP_TBL - IB) + 4 * g + 4])[0]
    tgt = IB + off
    nm = name_at(tgt)
    print("   internal type %2d (0x%02x) -> group %d -> 0x%x  %r" %
          (t, t, g, tgt, nm))

print()
print("== (B) PRP stream enum -> subscribe wrapper ==")
TBL = IB + 0xf86e4
enum_wrapper = {}
for i in range(0x1a):
    off = struct.unpack("<i", d[r2f(TBL - IB) + 4 * i:r2f(TBL - IB) + 4 * i + 4])[0]
    tgt = IB + off
    callee = None
    for ins in disasm(tgt, tgt + 0x60):
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            c = ins.operands[0].imm
            if 0x140273000 <= c <= 0x140283000:
                callee = c
                break
    enum_wrapper[i] = (tgt, callee)
    print("   enum %2d -> case 0x%x  first-call %s" % (i, tgt, hex(callee) if callee else "-"))

print()
print("== (C) wrappers: helper + internal type + selector ==")
for i, (tgt, w) in sorted(enum_wrapper.items()):
    if not w:
        continue
    b = fbnd(w)
    if not b:
        continue
    il = disasm(b[0], b[1])
    helper = None
    htype = None
    hreg = None
    for ins in il:
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            c = ins.operands[0].imm
            if c in (0x140277a40, 0x140277ba0, 0x140277c20):
                helper = c
                # look back for the edx/r8d immediate
                for x in il[:il.index(ins)]:
                    if x.mnemonic == "mov" and len(x.operands) == 2:
                        dst, src = x.operands
                        if src.type == X86_OP_IMM and dst.type == X86_OP_MEM and \
                                "edx" in x.op_str.split(",")[0]:
                            htype = src.imm
                            hreg = "edx"
                        elif src.type == X86_OP_IMM and "r8d" in x.op_str.split(",")[0]:
                            htype = src.imm
                            hreg = "r8d"
                break
    sel = 1 if helper == 0x140277a40 else 0
    print("   enum %2d -> wrapper 0x%x helper 0x%x type %s(%s) selector %d" %
          (i, w, helper or 0, htype, hreg, sel))

print()
print("== (D) stream_type_receiver: registry writes ==")
b = fbnd(0x140264c90)
il = disasm(b[0], b[1])
cur_id = None
for ins in il:
    if ins.mnemonic == "cmp" and len(ins.operands) == 2:
        dst, src = ins.operands
        if src.type == X86_OP_IMM and dst.type != X86_OP_MEM:
            cur_id = src.imm
    if ins.mnemonic == "mov" and len(ins.operands) == 2:
        dst, src = ins.operands
        if dst.type == X86_OP_MEM and src.type == X86_OP_IMM:
            if "0x10e8" in ins.op_str:
                print("   0x%x registryA[++] = %d   (near stream id %s)" %
                      (ins.address, src.imm, cur_id))
            elif "0x1818" in ins.op_str or "0x1890" in ins.op_str:
                print("   0x%x capsEntry field = %d  @%s" %
                      (ins.address, src.imm, ins.op_str))
