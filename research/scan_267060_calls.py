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

# Let's search inside 0x140267060 for other callbacks called:
f_off = va_to_offset(0x140267060)
with open('platform_runtime_service.exe', 'rb') as f:
    f.seek(f_off)
    code = f.read(0xa00)

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for i in md.disasm(code, 0x140267060):
    if i.mnemonic in ('call', 'jmp') and ('r' in i.op_str or 'qword' in i.op_str):
        print(f"0x{i.address:x}: {i.mnemonic:10s} {i.op_str}")
    elif '0x113' in i.op_str or '0x114' in i.op_str or '0x115' in i.op_str:
        print(f"0x{i.address:x}: {i.mnemonic:10s} {i.op_str}")
