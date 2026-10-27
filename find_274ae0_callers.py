import pefile
import struct

pe = pefile.PE('platform_runtime_service.exe')
image_base = pe.OPTIONAL_HEADER.ImageBase

target_va = 0x140274ae0

for s in pe.sections:
    name = s.Name.decode('latin1').strip('\x00')
    if name == '.text':
        sec_data = s.get_data()
        sec_va = image_base + s.VirtualAddress
        for offset in range(len(sec_data) - 5):
            if sec_data[offset] == 0xe8:
                disp = struct.unpack('<i', sec_data[offset+1:offset+5])[0]
                insn_next_va = sec_va + offset + 5
                if insn_next_va + disp == target_va:
                    raw_off = s.PointerToRawData + offset
                    print(f"Call to 0x140274ae0 at VA 0x{insn_next_va-5:x} (file offset 0x{raw_off:x})")
