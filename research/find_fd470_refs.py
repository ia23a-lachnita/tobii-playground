import pefile
import struct

pe = pefile.PE('platform_runtime_service.exe')
image_base = pe.OPTIONAL_HEADER.ImageBase

target_va = 0x1400fd470

with open('platform_runtime_service.exe', 'rb') as f:
    data = f.read()

# search for 8-byte pointer
va_bytes = struct.pack('<Q', target_va)
pos = 0
while True:
    pos = data.find(va_bytes, pos)
    if pos == -1: break
    print(f"Pointer at file offset 0x{pos:x}")
    pos += 8

# search for RIP relative
for s in pe.sections:
    name = s.Name.decode('latin1').strip('\x00')
    if name == '.text':
        sec_data = s.get_data()
        sec_va = image_base + s.VirtualAddress
        for offset in range(len(sec_data) - 4):
            disp = struct.unpack('<i', sec_data[offset:offset+4])[0]
            insn_next_va = sec_va + offset + 4
            if insn_next_va + disp == target_va:
                raw_off = s.PointerToRawData + offset
                print(f"RIP-rel ref in {name} at file offset 0x{raw_off-3:x} (VA 0x{insn_next_va-7:x})")
