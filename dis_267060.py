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

f_off = 0x266460
s = pe.sections[0]
rva = s.VirtualAddress + (f_off - s.PointerToRawData)
start_va = image_base + rva

with open('platform_runtime_service.exe', 'rb') as f:
    f.seek(f_off)
    code = f.read(0x100)

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for i in md.disasm(code, start_va):
    print(f"0x{i.address:x}: {i.mnemonic:10s} {i.op_str}")
