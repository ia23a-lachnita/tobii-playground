import pefile
pe = pefile.PE('platform_runtime_service.exe')
for s in pe.sections:
    name = s.Name.decode('latin1').strip('\x00')
    print(name, hex(s.PointerToRawData), hex(s.SizeOfRawData), hex(s.VirtualAddress), hex(s.Misc_VirtualSize))
