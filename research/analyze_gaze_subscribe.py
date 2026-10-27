#!/usr/bin/env python3
"""Decode the PRP-stream -> internal-stream-type mapping in the platform runtime.

Chain being decoded:
  client asks for PRP stream enum N
    -> device::subscribe  (switch on enum N, table at 0x1400f86e4)
    -> per-stream wrapper (descriptor: selector byte + requested INTERNAL type)
    -> general_stream_subscribe (searches ctx+0x10e8 / ctx+0x18f0 registry)
  registry is filled by stream_type_receiver (FUN_140264c90) from the device's
  reported stream ids.

Outputs a compact table so we can see which requested INTERNAL type is missing
from the registry for the gaze-point stream.

Usage: python analyze_gaze_subscribe.py [exe]
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

PRP_NAMES = {}
for m in re.finditer(rb"PRP_STREAM_ENUM_[A-Z0-9_]+", d):
    r = f2r(m.start())
    if r is not None:
        PRP_NAMES[IB + r] = m.group().decode()


def disasm(a, b):
    o = r2f(a - IB)
    return list(md.disasm(d[o:o + b - a], a))


# ------------------------------------------------------------------ 1) enum index table
# switch at 0x1400f548f: table base rdx+0xf59dc where rdx = 0x1400f59dc - ? use base guess
# The switch in device::subscribe is: mov ecx,[rdx + r9*4 + 0xf59dc]; add rcx,rdx
# where rdx = rip of the lea (0x1400f547b: lea rdx,[rip-0xf5482]) -> rdx = 0x1400f547b+7-0xf5482 = 0x1400f0000
# => table at 0x1400f0000+0xf59dc = 0x140ff59dc ; entries are dword offsets from 0x1400f0000
print("== PRP enum index -> name (from the jump table at 0x140ff59dc) ==")
BASE = IB
TBL = IB + 0xf59dc
enum_name = {}
for i in range(0x25):
    off = struct.unpack("<i", d[r2f(TBL - IB) + 4 * i:r2f(TBL - IB) + 4 * i + 4])[0]
    tgt = BASE + off
    # find the lea that loads the name at that target
    name = None
    for ins in disasm(tgt, tgt + 16):
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            src = ins.operands[1]
            if src.type == X86_OP_MEM and src.mem.base == X86_REG_RIP:
                name = PRP_NAMES.get(ins.address + ins.size + src.mem.disp)
                break
    enum_name[i] = name
    print("   enum %2d -> 0x%x  %s" % (i, tgt, name))

# ------------------------------------------------------------------ 2) subscribe switch
print()
print("== device::subscribe switch on PRP enum (table 0x1400f86e4, base 0x140000000) ==")
TBL2 = 0x1400f86e4
wrapper_of = {}
for i in range(0x1a):
    off = struct.unpack("<i", d[r2f(TBL2 - IB) + 4 * i:r2f(TBL2 - IB) + 4 * i + 4])[0]
    tgt = IB + off
    # walk the case body, find first call into 0x140274xxx..0x140283xxx range
    callee = None
    for ins in disasm(tgt, tgt + 0x90):
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            c = ins.operands[0].imm
            if 0x140274000 <= c <= 0x140283000:
                callee = c
                break
        if ins.mnemonic == "jmp" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            # case may jump to a shared block; follow one hop
            t2 = ins.operands[0].imm
            for ins2 in disasm(t2, t2 + 0x90):
                if ins2.mnemonic == "call" and ins2.operands and \
                        ins2.operands[0].type == X86_OP_IMM:
                    c = ins2.operands[0].imm
                    if 0x140274000 <= c <= 0x140283000:
                        callee = c
                        break
            break
    wrapper_of[i] = callee
    print("   enum %2d %-46s -> wrapper 0x%x" % (i, enum_name.get(i), callee or 0))

# ------------------------------------------------------------------ 3) wrappers
print()
print("== wrapper descriptors (selector byte, requested internal type) ==")
wrappers = sorted(set(v for v in wrapper_of.values() if v))
for w in wrappers:
    b = fbnd(w)
    if not b:
        continue
    # find the call to general_stream_subscribe 0x140273660 and dump the 40 bytes before
    for ins in disasm(b[0], b[1]):
        if ins.mnemonic == "call" and ins.operands and \
                ins.operands[0].type == X86_OP_IMM and ins.operands[0].imm == 0x140273660:
            pre = [x for x in disasm(max(b[0], ins.address - 0x50), ins.address)]
            sel = None
            typ = None
            for x in pre:
                if x.mnemonic == "mov" and len(x.operands) == 2:
                    dst, src = x.operands
                    if dst.type == X86_OP_MEM and src.type == X86_OP_IMM:
                        if dst.mem.disp in (0x40, 0x44, 0x48, 0x4c, 0x50) and \
                                "rsp" in x.op_str:
                            # descriptor fields live at [rsp+X]
                            pass
                if x.mnemonic == "mov" and len(x.operands) == 2:
                    dst, src = x.operands
                    if src.type == X86_OP_IMM and dst.type == X86_OP_MEM and \
                            dst.mem.base == 0 and dst.mem.index == 0:
                        pass
            # simpler: print the raw pre-call instructions
            print("\n   wrapper 0x%x (fn 0x%x..0x%x)" % (w, b[0], b[1]))
            for x in pre:
                mark = ""
                if x.mnemonic == "mov" and len(x.operands) == 2:
                    dst, src = x.operands
                    if src.type == X86_OP_IMM:
                        mark = "   <<< imm %d (0x%x)" % (src.imm, src.imm)
                    if dst.type == X86_OP_MEM and src.type == X86_OP_REG:
                        mark = "   <<< from %s" % x.op_str
                print("      0x%x  %-22s %s%s" % (x.address, x.mnemonic,
                                                    x.op_str, mark))
            break

# ------------------------------------------------------------------ 4) registry writes
print()
print("== stream_type_receiver: values written into ctx+0x10e8 (registry A) ==")
b = fbnd(0x140264c90)
for ins in disasm(b[0], b[1]):
    if ins.mnemonic == "mov" and len(ins.operands) == 2:
        dst, src = ins.operands
        if dst.type == X86_OP_MEM and src.type == X86_OP_IMM:
            if "0x10e8" in ins.op_str:
                print("   0x%x  %s %s   <<< registry A entry = %d" %
                      (ins.address, ins.mnemonic, ins.op_str, src.imm))
    if ins.mnemonic == "cmp" and len(ins.operands) == 2:
        dst, src = ins.operands
        if src.type == X86_OP_IMM and dst.type == X86_OP_REG:
            print("   0x%x  cmp %s, %d   <<< stream id dispatch" %
                  (ins.address, ins.op_str, src.imm))
