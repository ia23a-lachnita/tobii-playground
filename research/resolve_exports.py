#!/usr/bin/env python3
"""Resolve the x86 Stream Engine export table CORRECTLY and check whether the
deployed force-true stubs actually sit on the intended exports.

The PE export ordinal table stores the EAT INDEX directly (not ordinal-minus-base)
in the classic format, so the common "idx = ord - base" shortcut shifts every name
by one.  This script prints both conventions and resolves the address table, so the
mapping can be checked against the bytes actually found in the file.
"""
import struct
import sys

X86 = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\xursc\AppData\Local\TobiiGhost\app-1.14.1\x86\tobii_stream_engine.dll"

b = open(X86, "rb").read()

e = struct.unpack("<I", b[0x3C:0x40])[0]
coff = e + 4
nsec = struct.unpack("<H", b[coff + 2:coff + 4])[0]
so = coff + 20 + struct.unpack("<H", b[coff + 16:coff + 18])[0]
SEC = []
for i in range(nsec):
    s = so + i * 40
    nm = b[s:s + 8].rstrip(b"\x00").decode("latin1")
    vs, va, rs, rp = struct.unpack("<IIII", b[s + 8:s + 24])
    SEC.append((nm, va, vs, rs, rp))


def r2f(rva):
    for nm, va, vs, rs, rp in SEC:
        if va <= rva < va + max(vs, rs):
            return rp + (rva - va)
    return None


opt = coff + 20
magic = struct.unpack("<H", b[opt:opt + 2])[0]
imagebase = struct.unpack("<I", b[opt + 28:opt + 32])[0] if magic == 0x10B else \
    struct.unpack("<Q", b[opt + 24:opt + 32])[0]
ddoff = opt + (96 if magic == 0x10B else 112)
edir_rva = struct.unpack("<I", b[ddoff:ddoff + 4])[0]
ed = r2f(edir_rva)
base, nfuncs, nnames, afun, anames, aords = struct.unpack("<IIIIII", b[ed + 16:ed + 16 + 24])
af = r2f(afun)
nt = r2f(anames)
ot = r2f(aords)

print("imagebase=0x%x  base=%d  nfuncs=%d nnames=%d" % (imagebase, base, nfuncs, nnames))


def eat_rva(i):
    if i < 0 or i >= nfuncs:
        return None
    r, = struct.unpack("<I", b[af + i * 4:af + i * 4 + 4])
    return r


STUB = bytes.fromhex("8b4c240cc7010100000033c0c3")
CASEP = bytes.fromhex("b0015f5ec3")

entries = []
for i in range(nnames):
    nrva, = struct.unpack("<I", b[nt + i * 4:nt + i * 4 + 4])
    no = r2f(nrva)
    nm = b[no:b.index(b"\x00", no)].decode("latin1")
    ordv, = struct.unpack("<H", b[ot + i * 2:ot + i * 2 + 2])
    entries.append((nm, ordv))

print("\n%-42s %-6s %-9s %-9s %-9s" % ("name", "ordv", "idx=ordv", "idx=ord-1", "which"))
interesting = {}
for nm, ordv in entries:
    a = eat_rva(ordv)
    c = eat_rva(ordv - 1)
    fa = r2f(a) if a else None
    fc = r2f(c) if c else None
    interesting[nm] = (fa, fc)

TARGETS = {
    0x11CA30: "stub site 1 (claimed tobii_stream_supported)",
    0x11CB90: "stub site 2 (claimed tobii_capability_supported)",
    0x1239B0: "stub site 3 (claimed tobii_internal_stream_supported)",
    0x123B10: "stub site 4 (claimed tobii_internal_capability_supported)",
    0x12D58C: "case patch site",
    0x130E0B: "subscribe-gate patch site",
}

print("\n== which export owns each patched file offset ==")
for off, label in TARGETS.items():
    owner = [nm for nm, (fa, fc) in interesting.items() if fa == off or fc == off]
    print("  0x%06x  %-52s -> %s" % (off, label, owner or "(internal, no export)"))

print("\n== the four exports we care about ==")
for nm in ("tobii_stream_supported", "tobii_capability_supported",
           "tobii_internal_stream_supported", "tobii_internal_capability_supported",
           "tobii_gaze_point_subscribe", "tobii_api_create", "tobii_device_create",
           "tobii_error_message"):
    if nm not in interesting:
        print("  %-42s NOT EXPORTED" % nm)
        continue
    fa, fc = interesting[nm]
    print("  %-42s idx=ordv: file %s | idx=ord-1: file %s" %
          (nm, ("0x%06x" % fa) if fa else "-", ("0x%06x" % fc) if fc else "-"))
    if fa is not None:
        print("        bytes at idx=ordv target: %s" % b[fa:fa + 13].hex(" "))

print("\n== stub signature check at the 4 stub sites ==")
for off in (0x11CA30, 0x11CB90, 0x1239B0, 0x123B10):
    chunk = b[off:off + 13]
    print("  0x%06x: %s   %s" % (off, chunk.hex(" "), "STUB" if chunk == STUB else "NOT a stub"))
