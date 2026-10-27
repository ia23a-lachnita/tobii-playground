import pefile

pe = pefile.PE('platform_runtime_service.exe')
image_base = pe.OPTIONAL_HEADER.ImageBase

def va_to_offset(va):
    rva = va - image_base
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None

off = va_to_offset(0x14046c070)
with open('platform_runtime_service.exe', 'rb') as f:
    f.seek(off)
    print("String at 0x14046c070:", f.read(100).split(b'\x00')[0])
