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

# In 0x140260380, let's see what vtable was passed to 0x1402b2de0
# Let's inspect 0x140260380 more carefully to find the actual function pointers
with open('platform_runtime_service.exe', 'rb') as f:
    f.seek(va_to_offset(0x1402603f9))
    code = f.read(0x100)

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for i in md.disasm(code, 0x1402603f9):
    print(f"0x{i.address:x}: {i.mnemonic:10s} {i.op_str}")
