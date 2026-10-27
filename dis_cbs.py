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

cbs = [
    ("ebx=1 (0x1400fd570)", 0x1400fd570),
    ("ebx=2 (0x1400fd0f0)", 0x1400fd0f0),
    ("ebx=3 (0x1400fd670)", 0x1400fd670),
    ("ebx=4 (0x1400fd470)", 0x1400fd470),
]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

with open('platform_runtime_service.exe', 'rb') as f:
    for name, va in cbs:
        f_off = va_to_offset(va)
        f.seek(f_off)
        code = f.read(0x60)
        print(f"\n=== {name} ===")
        for i in md.disasm(code, va):
            print(f"0x{i.address:x}: {i.mnemonic:10s} {i.op_str}")
