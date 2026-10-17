"""Locate every 0x313/0x314 string occurrence with context in the patched
service binary, to determine whether there is a second default pid string."""
import re

PATH = r"C:\Users\xursc\projects\tobii_playground\platform_runtime_service.exe"
data = open(PATH, "rb").read()

for pat in (b"0x313", b"0x314", b"0x316", b"0313", b"0314"):
    hits = list(re.finditer(re.escape(pat), data))
    print(f"=== {pat}: {len(hits)} hits")
    for m in hits:
        pre = data[max(0, m.start() - 60):m.start()]
        post = data[m.end():m.end() + 60]
        pre_s = "".join(chr(b) if 32 <= b < 127 else "." for b in pre)
        post_s = "".join(chr(b) if 32 <= b < 127 else "." for b in post)
        print(f"  @ {hex(m.start())}  ...{pre_s} [{pat.decode()}] {post_s}...")
