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

targets = [
    ("fn0", 0x1402781c2 + 7 + 0x3b067),
    ("fn1", 0x1402781eb + 7 + 0x3b4ce),
    ("fn2", 0x140278214 + 7 + 0x3b6e5),
    ("fn3", 0x140278239 + 7 + 0x3b640),
]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

with open('platform_runtime_service.exe', 'rb') as f:
    for name, va in targets:
        f_off = va_to_offset(va)
        f.seek(f_off)
        code = f.read(0x30)
        print(f"\n=== {name} (0x{va:x}) ===")
        for i in md.disasm(code, va):
            print(f"0x{i.address:x}: {i.mnemonic:10s} {i.op_str}")
