#!/usr/bin/env python3
"""
Patch platform_runtime_service.exe to suppress TRACKER_ERROR_NOT_SUPPORTED
in general_stream_subscribe (0x1402784a0).
File offset 0x27799b:
  Original: 8b f0 85 c0 75 2e  (mov esi, eax; test eax, eax; jne 0x1402785cf)
  Patched:  31 f6 90 90 90 90  (xor esi, esi; nop; nop; nop; nop)
"""
import shutil
import sys
import capstone

SRC = "platform_runtime_service.exe"
BAK = "platform_runtime_service.exe.bak_userpos"

OFFSET = 0x27799b
ORIG_BYTES = bytes.fromhex("8bf085c0752e")
PATCH_BYTES = bytes.fromhex("31f690909090")

with open(SRC, "rb") as f:
    data = bytearray(f.read())

actual = data[OFFSET:OFFSET+len(ORIG_BYTES)]
if actual != ORIG_BYTES:
    print(f"ERROR: Expected {ORIG_BYTES.hex()} at 0x{OFFSET:x}, got {actual.hex()}")
    sys.exit(1)

shutil.copyfile(SRC, BAK)
print(f"Backed up {SRC} to {BAK}")

data[OFFSET:OFFSET+len(PATCH_BYTES)] = PATCH_BYTES

with open(SRC, "wb") as f:
    f.write(data)

print(f"Successfully patched {len(PATCH_BYTES)} bytes at 0x{OFFSET:x}")

# Verify disassembly with Capstone
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
with open(SRC, "rb") as f:
    f.seek(OFFSET - 5)
    code = f.read(25)

print("\n--- Disassembly after patch ---")
for i in md.disasm(code, 0x140278596):
    print(f"0x{i.address:x}: {i.mnemonic:10s} {i.op_str} (bytes: {i.bytes.hex()})")
