import capstone
import pefile

pe = pefile.PE('platform_runtime_service.exe')
image_base = pe.OPTIONAL_HEADER.ImageBase

file_offset = 0xf0d00
# convert to VA
s = pe.sections[0]
rva = s.VirtualAddress + (file_offset - s.PointerToRawData)
start_va = image_base + rva

with open('platform_runtime_service.exe', 'rb') as f:
    f.seek(file_offset)
    code = f.read(0x300)

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for i in md.disasm(code, start_va):
    cur_file_offset = file_offset + (i.address - start_va)
    print(f"0x{cur_file_offset:x} (0x{i.address:x}): {i.mnemonic:10s} {i.op_str}")
