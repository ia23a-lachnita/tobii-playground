import pefile
d1 = open('tobii_stream_engine.dll', 'rb').read()
d2 = open('x64_patched_tobii_stream_engine.dll', 'rb').read()
diffs = [i for i, (b1, b2) in enumerate(zip(d1, d2)) if b1 != b2]
print(f"Total diffs: {len(diffs)}")
for i in diffs[:20]:
    print(f"Offset 0x{i:x}: 0x{d1[i]:02x} -> 0x{d2[i]:02x}")
