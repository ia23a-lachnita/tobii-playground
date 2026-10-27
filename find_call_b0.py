import pefile
import struct

pe = pefile.PE('platform_runtime_service.exe')
image_base = pe.OPTIONAL_HEADER.ImageBase

with open('platform_runtime_service.exe', 'rb') as f:
    data = f.read()

# Search for calls to [ ... + 0xb0 ]
# In x64: call qword ptr [reg + 0xb0] -> ff 5x b0 or ff 9x b0 00 00 00
# or ff 10 / etc.
# Let's search in .text for 0x000000b0 with 0xff
for s in pe.sections:
    if s.Name.decode('latin1').strip('\x00') == '.text':
        sec = s.get_data()
        for i in range(len(sec) - 6):
            if sec[i] == 0xff and sec[i+2:i+6] == b'\xb0\x00\x00\x00':
                va = image_base + s.VirtualAddress + i
                raw = s.PointerToRawData + i
                print(f"Call [reg + 0xb0] at VA 0x{va:x} (file offset 0x{raw:x}): {sec[i:i+6].hex()}")
            if sec[i] == 0xff and sec[i+1] in (0x50, 0x51, 0x52, 0x53, 0x55, 0x56, 0x57) and sec[i+2] == 0xb0: # wait, 0xb0 is > 0x7f, so it must be disp32
                pass
