import pefile

pe = pefile.PE('platform_runtime_service.exe')
image_base = pe.OPTIONAL_HEADER.ImageBase

def va_to_offset(va):
    rva = va - image_base
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None

targets = [
    ("edx=0", 0x140277b55 + 7 + 0x1f44ec),
    ("edx=1", 0x140277b2b + 7 + 0x1f4526),
    ("edx=2", 0x140277b01 + 7 + 0x1f4568),
    ("edx=3", 0x140277a6e + 7 + 0x1f45bb),
]

with open('platform_runtime_service.exe', 'rb') as f:
    for name, va in targets:
        off = va_to_offset(va)
        f.seek(off)
        s = f.read(100).split(b'\x00')[0]
        print(f"{name}: VA 0x{va:x} -> {s}")
