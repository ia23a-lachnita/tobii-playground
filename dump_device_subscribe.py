import pefile
import capstone

pe = pefile.PE('platform_runtime_service.exe')
image_base = pe.OPTIONAL_HEADER.ImageBase

def va_to_offset(va):
    rva = va - image_base
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None

start_va = 0x1400f7a50
f_off = va_to_offset(start_va)
length = 0x1400f8650 - start_va

with open('platform_runtime_service.exe', 'rb') as f:
    f.seek(f_off)
    code = f.read(length)

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
lines = []
for i in md.disasm(code, start_va):
    cur_file_offset = f_off + (i.address - start_va)
    lines.append(f"0x{cur_file_offset:x} (0x{i.address:x}): {i.mnemonic:10s} {i.op_str}")

with open('device_subscribe.asm', 'w') as out:
    out.write('\n'.join(lines))

print(f"Wrote {len(lines)} lines to device_subscribe.asm")
