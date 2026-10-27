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
    0x1400f7270 + 7 + 0x34a3f1,
    0x1400f727c + 7 + 0x34a40d,
    0x1400f7288 + 7 + 0x34a429,
    0x1400f7294 + 7 + 0x34a44d,
    0x1400f72a0 + 7 + 0x34a471,
    0x1400f72ac + 7 + 0x34a49d,
]

with open('platform_runtime_service.exe', 'rb') as f:
    for idx, va in enumerate(targets):
        off = va_to_offset(va)
        f.seek(off)
        s = f.read(100).split(b'\x00')[0]
        print(f"Compound stream {idx}: VA 0x{va:x} -> {s.decode('latin1')}")
