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
    ("ebx=1", 0x1400fd5c4 + 7 + 0x3462e5),
    ("ebx=2", 0x1400fd144 + 7 + 0x346765),
    ("ebx=3", 0x1400fd6c4 + 7 + 0x3461e5),
    ("ebx=4", 0x1400fd4c4 + 7 + 0x3463e5),
]

with open('platform_runtime_service.exe', 'rb') as f:
    for name, va in targets:
        off = va_to_offset(va)
        f.seek(off)
        s = f.read(100).split(b'\x00')[0]
        print(f"{name}: VA 0x{va:x} -> {s}")
