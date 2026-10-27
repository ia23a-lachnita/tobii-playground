import capstone
import pefile

pe = pefile.PE('platform_runtime_service.exe')
image_base = pe.OPTIONAL_HEADER.ImageBase

file_offset = 0xf66a0
# convert file_offset to RVA
for s in pe.sections:
    raw_start = s.PointerToRawData
    raw_end = raw_start + s.SizeOfRawData
    if raw_start <= file_offset < raw_end:
        rva = s.VirtualAddress + (file_offset - raw_start)
        break

start_offset = max(0, file_offset - 0x60)
length = 0x120

with open('platform_runtime_service.exe', 'rb') as f:
    f.seek(start_offset)
    code = f.read(length)

start_va = image_base + (rva - (file_offset - start_offset))

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for i in md.disasm(code, start_va):
    cur_file_offset = file_offset + (i.address - (image_base + rva))
    mark = " --> " if cur_file_offset == file_offset else "     "
    print(f"{mark}0x{cur_file_offset:x} (0x{i.address:x}): {i.mnemonic} {i.op_str}")
