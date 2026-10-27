#!/usr/bin/env python3
"""Dump the x86 Stream Engine export table with RVA and file offsets."""
import struct
import sys

X86 = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\xursc\AppData\Local\TobiiGhost\app-1.14.1\x86\tobii_stream_engine.dll"

b = open(X86, "rb").read()


def sections():
    e = struct.unpack("<I", b[0x3C:0x40])[0]
    coff = e + 4
    n = struct.unpack("<H", b[coff + 2:coff + 4])[0]
    so = coff + 20 + struct.unpack("<H", b[coff + 16:coff + 18])[0]
    out = []
    for i in range(n):
        s = so + i * 40
        name = b[s:s + 8].rstrip(b"\x00").decode("latin1")
        vs, va, rs, rp = struct.unpack("<IIII", b[s + 8:s + 24])
        out.append((name, va, vs, rs, rp))
    return out


S = sections()


def r2f(rva):
    for name, va, vs, rs, rp in S:
        if va <= rva < va + max(vs, rs):
            return rp + (rva - va)
    return None


e = struct.unpack("<I", b[0x3C:0x40])[0]
opt = e + 4 + 20
magic = struct.unpack("<H", b[opt:opt + 2])[0]
imagebase = struct.unpack("<I", b[opt + 28:opt + 32])[0] if magic == 0x10B else \
    struct.unpack("<Q", b[opt + 24:opt + 32])[0]
ddoff = opt + (96 if magic == 0x10B else 112)
edir_rva, edir_size = struct.unpack("<II", b[ddoff:ddoff + 8])
ed = r2f(edir_rva)
base, nfuncs, nnames, afun, anames, aords = struct.unpack("<IIIIII", b[ed + 16:ed + 16 + 24])
af = r2f(afun)
nt = r2f(anames)
ot = r2f(aords)

print("imagebase 0x%x  export base ordinal %d  #names %d" % (imagebase, base, nnames))
print("\n%-44s %-10s %-10s" % ("export", "rva", "file"))
wanted = ("gaze", "stream_supported", "capability_supported", "api_create",
          "device_create", "subscribe", "error_message")
for i in range(nnames):
    nrva, = struct.unpack("<I", b[nt + i * 4:nt + i * 4 + 4])
    no = r2f(nrva)
    nm = b[no:b.index(b"\x00", no)].decode("latin1")
    ordv, = struct.unpack("<H", b[ot + i * 2:ot + i * 2 + 2])
    idx = ordv - base
    if 0 <= idx < nfuncs:
        frva, = struct.unpack("<I", b[af + idx * 4:af + idx * 4 + 4])
        fo = r2f(frva)
        mark = "  <<<" if any(w in nm for w in wanted) else ""
        print("%-44s 0x%08x  %s%s" % (nm, frva, ("0x%06x" % fo) if fo else "-", mark))
