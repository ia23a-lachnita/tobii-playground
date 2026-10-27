import pefile

pe = pefile.PE('x64_patched_tobii_stream_engine.dll')
if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
    for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        if exp.name:
            n = exp.name.decode('latin1')
            if 'guide' in n.lower() or 'position' in n.lower() or 'user' in n.lower():
                print(n)
