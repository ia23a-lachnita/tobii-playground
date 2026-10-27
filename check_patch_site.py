import capstone

with open('platform_runtime_service.exe', 'rb') as f:
    f.seek(0x277990)
    code = f.read(0x30)

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for i in md.disasm(code, 0x140278590):
    print(f"0x{i.address:x}: {i.mnemonic:10s} {i.op_str} (bytes: {i.bytes.hex()})")
