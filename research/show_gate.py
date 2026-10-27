#!/usr/bin/env python3
"""Show the subscribe-gate bytes at file 0x130e04 in every x86 copy."""
import hashlib

FILES = [
    r"C:\Users\xursc\Downloads\TobiiGhost_Extract\lib\native\x86\tobii_stream_engine.dll",
    r"C:\Users\xursc\AppData\Local\TobiiGhost\app-1.14.1\x86\tobii_stream_engine.dll",
    r"C:\Users\xursc\AppData\Local\TobiiGhost\app-1.14.1\tobii_stream_engine.dll",
    r"C:\Users\xursc\projects\tobii_playground\x86_patched_tobii_stream_engine.dll",
]

for p in FILES:
    d = open(p, "rb").read()
    print("%-74s sha %s" % (p, hashlib.sha256(d).hexdigest()[:16]))
    print("    0x130e04: %s" % d[0x130E04:0x130E10].hex(" "))
    print("    gate byte @0x130e0b = 0x%02x (%s)" %
          (d[0x130E0B], "jnz -> wants EB" if d[0x130E0B] == 0x75 else "already patched"))
