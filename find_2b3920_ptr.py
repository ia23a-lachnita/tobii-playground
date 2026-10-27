import pefile
import struct

pe = pefile.PE('platform_runtime_service.exe')
image_base = pe.OPTIONAL_HEADER.ImageBase

target_va = 0x1402b3920
target_bytes = struct.pack('<Q', target_va)

with open('platform_runtime_service.exe', 'rb') as f:
    data = f.read()

pos = 0
while True:
    pos = data.find(target_bytes, pos)
    if pos == -1: break
    print(f"Pointer at file offset 0x{pos:x}")
    pos += 8
