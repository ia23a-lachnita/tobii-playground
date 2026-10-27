import pefile, capstone
pe = pefile.PE('x64_patched_tobii_stream_engine.dll')
base = pe.OPTIONAL_HEADER.ImageBase
for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
    if exp.name == b'tobii_gaze_data_subscribe':
        rva = exp.address
        code = pe.get_data(rva, 96)
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        for i in md.disasm(code, base + rva):
            print(f'{i.address:x}: {i.mnemonic} {i.op_str}')
