import pefile
import struct

pe = pefile.PE('platform_runtime_service.exe')
image_base = pe.OPTIONAL_HEADER.ImageBase

with open('platform_runtime_service.exe', 'rb') as f:
    data = f.read()

target = 0x11400
b = struct.pack('<I', target)
pos = 0
while True:
    pos = data.find(b, pos)
    if pos == -1: break
    print(f"0x11400 found at file offset 0x{pos:x}")
    pos += 4
