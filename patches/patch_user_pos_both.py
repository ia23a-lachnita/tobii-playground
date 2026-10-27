#!/usr/bin/env python3
"""
Patch platform_runtime_service.exe so User Position Guide activates both
stream 5 and stream 0xb (the same streams that GAZE_POINT activates).
"""
import capstone

SRC = "platform_runtime_service.exe"

with open(SRC, "rb") as f:
    data = bytearray(f.read())

OFF_SUB = 0x27857d
# mov byte ptr [rcx + 5], 1 (c6 41 05 01)
# mov byte ptr [rcx + 0xb], 1 (c6 41 0b 01)
# ret (c3)
PATCH_SUB = bytes.fromhex("c6410501c6410b01c3")
data[OFF_SUB:OFF_SUB+len(PATCH_SUB)] = PATCH_SUB
print(f"Patched subscribe setup at 0x{OFF_SUB:x}")

OFF_UNSUB = 0x2785bd
# mov byte ptr [rcx + 5], 0 (c6 41 05 00)
# mov byte ptr [rcx + 0xb], 0 (c6 41 0b 00)
# ret (c3)
PATCH_UNSUB = bytes.fromhex("c6410500c6410b00c3")
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
