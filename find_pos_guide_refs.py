import pefile

pe = pefile.PE('platform_runtime_service.exe')
image_base = pe.OPTIONAL_HEADER.ImageBase
print(f"Image base: 0x{image_base:x}")

# Find section for file offset 0x43ff18
target_offset = 0x43ff18
target_rva = None
for s in pe.sections:
    name = s.Name.decode('latin1').strip('\x00')
    raw_start = s.PointerToRawData
    raw_end = raw_start + s.SizeOfRawData
    if raw_start <= target_offset < raw_end:
        target_rva = s.VirtualAddress + (target_offset - raw_start)
        print(f"0x{target_offset:x} is in section {name}, RVA = 0x{target_rva:x}, VA = 0x{image_base + target_rva:x}")
        break

# Let's search for references to VA or RVA or string in .text / .rdata
target_va = image_base + target_rva
import struct
va_bytes = struct.pack('<Q', target_va)

with open('platform_runtime_service.exe', 'rb') as f:
    data = f.read()

pos = 0
while True:
    pos = data.find(va_bytes, pos)
    if pos == -1: break
    print(f"Pointer to string at file offset 0x{pos:x}")
    pos += 8

# Also search for lea rxx, [target_va] (rip-relative)
for s in pe.sections:
    name = s.Name.decode('latin1').strip('\x00')
    if name in ('.text', '.rdata'):
        sec_data = s.get_data()
        sec_va = image_base + s.VirtualAddress
        # RIP relative offset: disp32 = target_va - (insn_va + 7 or insn_va + 4)
        for offset in range(len(sec_data) - 4):
            disp = struct.unpack('<i', sec_data[offset:offset+4])[0]
            insn_next_va = sec_va + offset + 4
            if insn_next_va + disp == target_va:
                raw_off = s.PointerToRawData + offset
                print(f"RIP-rel ref in {name} at file offset 0x{raw_off-3:x} (disp offset 0x{raw_off:x})")
