#!/usr/bin/env python3
"""Extract, for every general_stream_subscribe call site, the stream descriptor
that is built on the stack: the registry-selector byte (offset 0) and the
requested internal stream type (dword at offset +4), plus any RIP-relative
string that identifies the stream.

The descriptor is a stack struct whose base is rsp (or r11=rsp) at the call.
We therefore print every `mov [reg+disp], imm` store into that stack frame in
the 0x100 bytes preceding each call, and resolve RIP-relative LEAs to strings.

Usage: python dis_subscribe_desc.py [path-to-exe]
"""
import re
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM

PATH = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
IMAGEBASE = 0x140000000
TARGET = 0x140273660

CALLERS = [0x140274ae0, 0x140274ca0, 0x140274e50, 0x140275000, 0x1402751a0,
           0x140275360, 0x140275520, 0x140275e10, 0x140275fc0, 0x140276170,
           0x140276330, 0x1402764f0, 0x140276700, 0x1402768b0, 0x140276a60,
           0x140276c20, 0x140276dd0, 0x1402770b0, 0x140277260, 0x140277410,
           0x1402777e0]

d = open(PATH, "rb").read()

# section table for RVA -> file
e = struct.unpack("<I", d[0x3C:0x40])[0]
coff = e + 4
nsec = struct.unpack("<H", d[coff + 2:coff + 4])[0]
so = coff + 20 + struct.unpack("<H", d[coff + 16:coff + 18])[0]
SECS = []
for i in range(nsec):
    s = so + i * 40
    nm = d[s:s + 8].rstrip(b"\x00").decode("latin1")
    vs, va, rs, rp = struct.unpack("<IIII", d[s + 8:s + 24])
    SECS.append((nm, va, vs, rp, rs))


def rva2file(rva):
    for nm, va, vs, rp, rs in SECS:
        if va <= rva < va + max(vs, rs):
            return rp + (rva - va)
    return None


def cstr(rva, maxlen=120):
    off = rva2file(rva)
    if off is None:
        return None
    end = d.find(b"\x00", off, off + maxlen)
    if end < 0:
        return None
    raw = d[off:end]
    try:
        s = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    return s if all(32 <= ord(c) < 127 for c in s) else None


md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
md.skipdata = True

for c in CALLERS:
    start = c - 0x100
    fo = start - 0xC00 + 0x400 - 0x400   # VA->file for .text: file = rva - 0xc00
    fo = (start - IMAGEBASE) - 0xC00
    insns = list(md.disasm(d[fo:fo + 0x120], start))
    print("\n=== call site VA 0x%x ===" % c)
    for ins in insns:
        if ins.address > c:
            break
        note = ""
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            if ins.operands[0].imm == TARGET:
                note = "   <<< CALL general_stream_subscribe"
        # stack immediate stores
        if ins.mnemonic == "mov" and len(ins.operands) == 2:
            dst, src = ins.operands
            if dst.type == X86_OP_MEM and src.type == X86_OP_IMM:
                base = ins.reg_name(dst.mem.base) if dst.mem.base else ""
                if base in ("rsp", "r11", "rbp") and 0 <= dst.mem.disp < 0x60:
                    note = "   <<< DESC[%d] = %d (0x%x)" % (
                        dst.mem.disp, src.imm, src.imm)
            # rip-relative string
            if dst.type == X86_OP_MEM and dst.mem.base == 0 and dst.mem.disp:
                pass
        if ins.mnemonic == "lea" and len(ins.operands) == 2:
            dst, src = ins.operands
            if src.type == X86_OP_MEM and src.mem.base == 0 and src.mem.disp:
                rva = src.mem.disp - IMAGEBASE
                s = cstr(rva)
                if s:
                    note = "   <<< STR %r" % s[:90]
        if note or ins.address == c:
            print("  0x%x  %-28s %s%s" % (ins.address, ins.mnemonic,
                                           ins.op_str, note))
