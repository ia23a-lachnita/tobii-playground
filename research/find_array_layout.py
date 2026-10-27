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

target_va = 0x140278150
f_off = va_to_offset(target_va)

with open('platform_runtime_service.exe', 'rb') as f:
    f.seek(f_off)
    code = f.read(0x300)

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
lines = []
for i in md.disasm(code, target_va):
    if any(k in i.op_str for k in ('[rsp', '[rbp', '[rbx', '[rcx', 'call', 'jmp')):
        lines.append(f"0x{i.address:x}: {i.mnemonic:10s} {i.op_str}")

with open('array_layout.asm', 'w') as out:
    out.write('\n'.join(lines))

print(f"Wrote {len(lines)} lines")
