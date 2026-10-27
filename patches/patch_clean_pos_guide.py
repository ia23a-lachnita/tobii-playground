#!/usr/bin/env python3
"""
Patch platform_runtime_service.exe to configure User Position Guide stream
to request stream 5 (gaze/camera) instead of stream 2 (unknown to 5L):

1. At 0x27857d (subscribe setup fn):
     c6 41 02 00     mov byte ptr [rcx + 2], 0   (do NOT request stream 2 from tracker)
     c6 41 05 01     mov byte ptr [rcx + 5], 1   (request stream 5 from tracker)
     c3              ret

2. At 0x2785bd (unsubscribe setup fn):
     c6 41 02 00     mov byte ptr [rcx + 2], 0
     c6 41 05 00     mov byte ptr [rcx + 5], 0
     c3              ret
"""
import shutil
import sys
import capstone

SRC = "platform_runtime_service.exe"

with open(SRC, "rb") as f:
    data = bytearray(f.read())

OFF_SUB = 0x27857d
PATCH_SUB = bytes.fromhex("c6410200c6410501c3")
data[OFF_SUB:OFF_SUB+len(PATCH_SUB)] = PATCH_SUB
print(f"Patched subscribe setup at 0x{OFF_SUB:x}")

OFF_UNSUB = 0x2785bd
PATCH_UNSUB = bytes.fromhex("c6410200c6410500c3")
data[OFF_UNSUB:OFF_UNSUB+len(PATCH_UNSUB)] = PATCH_UNSUB
print(f"Patched unsubscribe setup at 0x{OFF_UNSUB:x}")

with open(SRC, "wb") as f:
    f.write(data)

# Disassemble both
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
with open(SRC, "rb") as f:
    f.seek(OFF_SUB)
    code1 = f.read(15)
    f.seek(OFF_UNSUB)
    code2 = f.read(15)

print("\n--- Disassembly at 0x27857d (subscribe) ---")
for i in md.disasm(code1, 0x14027917d):
    print(f"0x{i.address:x}: {i.mnemonic:10s} {i.op_str} (bytes: {i.bytes.hex()})")

print("\n--- Disassembly at 0x2785bd (unsubscribe) ---")
for i in md.disasm(code2, 0x1402791bd):
    print(f"0x{i.address:x}: {i.mnemonic:10s} {i.op_str} (bytes: {i.bytes.hex()})")
