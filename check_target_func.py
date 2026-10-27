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

# Check string at 0x1404420d0
off = va_to_offset(0x1404420d0)
with open('platform_runtime_service.exe', 'rb') as f:
    f.seek(off)
    print("String at 0x1404420d0:", f.read(100).split(b'\x00')[0])

# Disassemble 0x1400f7a50
f_off = va_to_offset(0x1400f7a50)
print(f"0x1400f7a50 file offset: 0x{f_off:x}")
with open('platform_runtime_service.exe', 'rb') as f:
    f.seek(f_off)
    code = f.read(0x100)

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for i in md.disasm(code, 0x1400f7a50):
    cur_file_offset = f_off + (i.address - 0x1400f7a50)
    print(f"0x{cur_file_offset:x} (0x{i.address:x}): {i.mnemonic:10s} {i.op_str}")
