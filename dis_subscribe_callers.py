#!/usr/bin/env python3
"""Disassemble the general_stream_subscribe call sites and show the stream-type
constant each wrapper passes.

general_stream_subscribe (FUN_140273660) takes a descriptor whose first 8
bytes are:  byte0 = registry selector (0 -> registry A at ctx+0x10e8),
                                  (non-zero -> registry B at ctx+0x18f0)
             dword at +4 = requested INTERNAL STREAM TYPE
It returns 3 (NOT_SUPPORTED) when that type is absent from the registry.

The 21 call sites are at VAs 0x140274ae0 .. 0x1402777e0.  For each we print the
preceding instructions so the type constant (mov dword ptr [rsp+X], imm) and the
registry selector byte are visible.

Usage: python dis_subscribe_callers.py [path-to-exe]
"""
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs

PATH = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
IMAGEBASE = 0x140000000
TEXT_VA = 0x140001000
TEXT_FILE = 0x400
DELTA = TEXT_VA - TEXT_FILE          # VA = file + DELTA
TARGET = 0x140273660

CALLERS = [0x140274ae0, 0x140274ca0, 0x140274e50, 0x140275000, 0x1402751a0,
           0x140275360, 0x140275520, 0x140275e10, 0x140275fc0, 0x140276170,
           0x140276330, 0x1402764f0, 0x140276700, 0x1402768b0, 0x140276a60,
           0x140276c20, 0x140276dd0, 0x1402770b0, 0x140277260, 0x140277410,
           0x1402777e0]

d = open(PATH, "rb").read()
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True


def dis(from_va, to_va):
    fo = from_va - DELTA
    return list(md.disasm(d[fo:fo + (to_va - from_va)], from_va))


for c in CALLERS:
    print("\n=== call site VA 0x%x (file 0x%x) ===" % (c, c - DELTA))
    start = c - 0x60
    for ins in dis(start, c + 0x10):
        mark = "  <<< CALL general_stream_subscribe" if ins.address == c else ""
        print("  0x%x  %-28s %s%s" % (ins.address, ins.mnemonic, ins.op_str, mark))
