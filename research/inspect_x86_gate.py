#!/usr/bin/env python3
"""Read-only inspection of the x86 client DLL internal capability gate.

FUN_1012e170 (file 0x12d570) is the INTERNAL stream_supported gate that the
subscribe path calls directly (the public export at 0x11ca30 is bypassed).
Main path:  ctx+0x4d8 != NULL  -> switch(param_2) with case 0/1/2/5
Fallback:   ctx+0x4d8 == NULL  -> local arrays, returns false for gaze ids

This script only REPORTS bytes and candidate code caves.
"""
import hashlib
import sys

X86 = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\xursc\Downloads\TobiiGhost_Extract\lib\native\x86\tobii_stream_engine.dll"

d = open(X86, "rb").read()
print("file: %s" % X86)
print("sha : %s  size %d" % (hashlib.sha256(d).hexdigest()[:16], len(d)))

ENTRY = 0x12D570          # FUN_1012e170 entry (VA 0x1012e170)
CASE = 0x12D58C           # patched case block inside the same function
print("\n== internal gate FUN_1012e170 ==")
print(" entry 0x%06x: %s" % (ENTRY, d[ENTRY:ENTRY + 24].hex(" ")))
print(" case  0x%06x: %s" % (CASE, d[CASE:CASE + 20].hex(" ")))

# decode the prologue by hand: 56 8b f1 57 8b fa = push esi; mov esi,ecx; push edi; mov edi,edx
pro = d[ENTRY:ENTRY + 6]
print(" prologue bytes: %s -> %s" % (pro.hex(" "),
      "push esi; mov esi,ecx; push edi; mov edi,edx" if pro.hex() == "568bf1578bfa" else "UNEXPECTED"))
body = ENTRY + 6
print(" BODY (fallback target after prologue) = 0x%06x : %s" % (body, d[body:body + 12].hex(" ")))

print("\n== candidate code caves (runs of 0xCC >= 40 bytes, .text area) ==")
caves = []
i = 0x12D000
while i < min(len(d) - 40, 0x160000):
    if d[i] == 0xCC:
        j = i
        while j < len(d) and d[j] == 0xCC:
            j += 1
        if j - i >= 40:
            caves.append((i, j - i))
        i = j
    else:
        i += 1
caves.sort(key=lambda c: abs(c[0] - 0x14F93D))
for off, ln in caves[:12]:
    print("  cave 0x%06x len %d  (dist to 0x14f93d: %+d)" % (off, ln, off - 0x14F93D))
print(" total caves >=40B: %d" % len(caves))

if 0x14F93D in [c[0] for c in caves]:
    off = 0x14F93D
    print("\n== cave at 0x14f93d detail ==")
    print("  bytes 0x14f93d..0x14f980: %s" % d[off:off + 68].hex(" "))
    print("  length of run: %d" % next(ln for o, ln in caves if o == off))
else:
    print("\n  cave 0x14f93d is NOT a clean 0xCC run in this file")

print("\n== bytes around the subscribe caller (for reference) ==")
# FUN_10131960 -> file 0x130D60 ; JNZ gate at VA 0x10131a0b -> file 0x130E0B
FUN = 0x130D60
print("  FUN_10131960 @0x%06x: %s" % (FUN, d[FUN:FUN + 16].hex(" ")))
print("  gate call/JNZ region @0x130E04: %s" % d[0x130E04:0x130E16].hex(" "))
