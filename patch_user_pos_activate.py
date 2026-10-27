#!/usr/bin/env python3
"""
Patch platform_runtime_service.exe to automatically activate stream 5 (gaze/camera)
whenever User Position Guide stream is subscribed/unsubscribed:

1. At 0x27857d:
   Original:
     c6 41 02 01     mov byte ptr [rcx + 2], 1
     c3              ret
     cc cc cc ...    padding
   Patched:
     c6 41 02 01     mov byte ptr [rcx + 2], 1
     c6 41 05 01     mov byte ptr [rcx + 5], 1
     c3              ret

2. At 0x2785bd:
   Original:
     c6 41 02 00     mov byte ptr [rcx + 2], 0
     c3              ret
     cc cc cc ...    padding
   Patched:
     c6 41 02 00     mov byte ptr [rcx + 2], 0
     c6 41 05 00     mov byte ptr [rcx + 5], 0
     c3              ret
"""
import shutil
import sys
import capstone

SRC = "platform_runtime_service.exe"
BAK = "platform_runtime_service.exe.bak_activate"

shutil.copyfile(SRC, BAK)
print(f"Backed up to {BAK}")

with open(SRC, "rb") as f:
    data = bytearray(f.read())

OFF_SUB = 0x27857d
EXPECT_SUB = bytes.fromhex("c6410201c3")
PATCH_SUB = bytes.fromhex("c6410201c6410501c3")

if data[OFF_SUB:OFF_SUB+len(EXPECT_SUB)] != EXPECT_SUB:
    print(f"ERROR: Expected {EXPECT_SUB.hex()} at 0x{OFF_SUB:x}, got {data[OFF_SUB:OFF_SUB+len(EXPECT_SUB)].hex()}")
    sys.exit(1)

data[OFF_SUB:OFF_SUB+len(PATCH_SUB)] = PATCH_SUB
print(f"Patched subscribe handler at 0x{OFF_SUB:x}")

OFF_UNSUB = 0x2785bd
EXPECT_UNSUB = bytes.fromhex("c6410200c3")
PATCH_UNSUB = bytes.fromhex("c6410200c6410500c3")

if data[OFF_UNSUB:OFF_UNSUB+len(EXPECT_UNSUB)] != EXPECT_UNSUB:
    print(f"ERROR: Expected {EXPECT_UNSUB.hex()} at 0x{OFF_UNSUB:x}, got {data[OFF_UNSUB:OFF_UNSUB+len(EXPECT_UNSUB)].hex()}")
    sys.exit(1)

data[OFF_UNSUB:OFF_UNSUB+len(PATCH_UNSUB)] = PATCH_UNSUB
print(f"Patched unsubscribe handler at 0x{OFF_UNSUB:x}")

with open(SRC, "wb") as f:
    f.write(data)

# Disassemble both to verify
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
