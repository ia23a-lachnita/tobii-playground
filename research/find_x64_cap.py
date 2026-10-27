import pefile, capstone
pe = pefile.PE('x64_patched_tobii_stream_engine.dll')
base = pe.OPTIONAL_HEADER.ImageBase
for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
    if exp.name == b'tobii_capability_supported':
        print(f"tobii_capability_supported RVA: 0x{exp.address:x}")
        code = pe.get_data(exp.address, 48)
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        for i in md.disasm(code, base + exp.address):
            print(f'{i.address:x}: {i.mnemonic} {i.op_str}')
