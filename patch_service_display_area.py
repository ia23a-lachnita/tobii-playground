#!/usr/bin/env python3
"""Patch platform_runtime_service.exe to enforce real monitor display area geometry.

Patch Sites:
1. File offset 0x260a45 (VA 0x140261645, 109 bytes):
   Device initialization / startup setup.
2. File offset 0x2675ac (VA 0x1402681ac, 81 bytes):
   Property 6 notification handler.

Geometry (Acer 27" 165Hz: 597.9 x 336.2 mm, 5 deg tilt):
  TL: (-298.95, 348.92, 14.30)
  TR: ( 298.95, 348.92, 14.30)
  BL: (-298.95,  14.00, -15.00)
"""

import os
import shutil
import struct
import sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

EXE = sys.argv[1] if len(sys.argv) > 1 else "platform_runtime_service.exe"

vals = [
    ("TL_x", -298.95),
    ("TL_y", 348.92),
    ("TL_z", 14.30),
    ("TR_x", 298.95),
    ("TR_y", 348.92),
    ("TR_z", 14.30),
    ("BL_x", -298.95),
    ("BL_y", 14.00),
    ("BL_z", -15.00),
]

def build_payload(base_reg, total_len):
    # lea rdx, [base_reg + 0xaf4c]
    asm = bytearray()
    if base_reg == 'rdi':
        asm.extend(bytes.fromhex("48 8d 97 4c af 00 00"))
    elif base_reg == 'rbx':
        asm.extend(bytes.fromhex("48 8d 93 4c af 00 00"))
    else:
        raise ValueError(base_reg)

    for i, (name, val) in enumerate(vals):
        disp = i * 4
        ins = bytes([0xc7, 0x42, disp]) + struct.pack('<f', val)
        asm.extend(ins)

    assert len(asm) <= total_len
    asm.extend(b'\x90' * (total_len - len(asm)))
    return asm

payload_init = build_payload('rdi', 109)
payload_notif = build_payload('rbx', 81)

def main():
    data = bytearray(open(EXE, "rb").read())

    # Patch site 1: startup init
    fo1 = 0x260a45
    data[fo1:fo1+len(payload_init)] = payload_init
    print(f"[+] Patched site 1 (startup init) at 0x{fo1:x} ({len(payload_init)} bytes)")

    # Patch site 2: property notification
    fo2 = 0x2675ac
    data[fo2:fo2+len(payload_notif)] = payload_notif
    print(f"[+] Patched site 2 (property notif) at 0x{fo2:x} ({len(payload_notif)} bytes)")

    with open(EXE, "wb") as f:
        f.write(data)

    # Verification with Capstone
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    print("\n[+] Verification of site 1 disassembly:")
    for ins in md.disasm(payload_init[:77], 0x140261645):
        print(f"  0x{ins.address:x}: {ins.bytes.hex(' '):24} {ins.mnemonic} {ins.op_str}")

    print("\n[+] Verification of site 2 disassembly:")
    for ins in md.disasm(payload_notif[:77], 0x1402681ac):
        print(f"  0x{ins.address:x}: {ins.bytes.hex(' '):24} {ins.mnemonic} {ins.op_str}")

if __name__ == "__main__":
    main()
