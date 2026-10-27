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

callers = [
    0x140274894,
    0x140274b80,
    0x140274d41,
    0x140274ef1,
    0x14027509e,
]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

with open('platform_runtime_service.exe', 'rb') as f:
    for c_va in callers:
        f_off = va_to_offset(c_va - 0x20)
        f.seek(f_off)
        code = f.read(0x30)
        print(f"=== Caller at 0x{c_va:x} ===")
        for i in md.disasm(code, c_va - 0x20):
            print(f"0x{i.address:x}: {i.mnemonic:10s} {i.op_str}")
