#!/usr/bin/env python3
"""Disassemble the castor stream_type_receiver ladder.

FUN_140264c90 (VA 0x140264c90) dispatches on the DEVICE-reported stream id
and, per branch, publishes an INTERNAL stream-type id into registry A:
    int registryA[] at ctx+0x10e8, count at ctx+0x14e8
general_stream_subscribe (FUN_140273660) refuses any subscribe whose
requested stream type is NOT in registry A -> returns 3 (NOT_SUPPORTED).

File mapping for platform_runtime_service.exe:
    rva = file + 0xc00 ; VA = 0x140000000 + rva
"""
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_MEM, X86_OP_IMM

PATH = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"
START_VA = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x140264C90
LENGTH = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x600

d = open(PATH, "rb").read()
start_rva = START_VA - 0x140000000
start_file = start_rva - 0xC00
code = d[start_file:start_file + LENGTH]

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True

REG_A = 0x10E8
CNT = 0x14E8

for ins in md.disasm(code, START_VA):
    note = ""
    ops = ins.operands
    if ops and ops[0].type == X86_OP_IMM:
        imm = ops[0].imm
        if imm in (1, 2, 3, 4, 5, 7, 8, 9, 0xC, 0xD, 0xE, 0xF, 0x10, 0x11,
                   0x12, 0x15, 0x16, 0x17, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E,
                   0x1F, 0x20, 0x21):
            note = "   <<< CMP device-stream-id %d" % imm
        elif 0 <= imm <= 0x30:
            note = "   <<< internal stream-type %d" % imm
    if ops and ops[0].type == X86_OP_MEM:
        m = ops[0].mem
        if m.disp == REG_A:
            note = "   <<< WRITE registryA[%rax] (ctx+0x10e8)"
        elif m.disp == CNT:
            note = "   <<< registryA count (ctx+0x14e8)"
        elif m.disp == 0x18F0:
            note = "   <<< registryB (ctx+0x18f0)"
    print("0x%x  %-30s %s%s" % (ins.address, ins.mnemonic, ins.op_str, note))
