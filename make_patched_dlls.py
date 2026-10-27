#!/usr/bin/env python3
"""Regenerate the patched Tobii client DLLs from the pristine originals.

Everything is derived from the pristine files in the TobiiGhost extract, so the
output is deterministic and byte-identical to what gets installed.

Why this script exists
----------------------
* The x86 "case patch" that was shipped in the deployed DLL NOPed the
  `pop edi` / `pop esi` stack cleanup of that switch case, so every call
  through that case leaked 8 bytes of stack.  The correct patch keeps the pops.
* The previously committed repo artifact `x86_patched_tobii_stream_engine.dll`
  was 4 bytes larger than the pristine file (4 bytes inserted without updating
  the section table), which made its export directory unreadable.
* The deployed x64 DLL had a bogus 5-byte JMP planted at an offset that was
  actually an RVA; it destroyed an unrelated function and jumped into `int3`
  padding, and the intended force-true patch was never applied.

Offsets (verified with a stdlib PE parser + capstone, see FINDINGS.md)

x86 (imagebase 0x10000000, .text: file = rva - 0x4600)
  tobii_stream_supported             file 0x11ca30
  tobii_capability_supported         file 0x11cb90
  tobii_internal_stream_supported    file 0x1239b0
  tobii_internal_capability_supported file 0x123b10
  switch-case block                  file 0x12d58c   (5 bytes)

x64 (imagebase 0x180000000, .text: file = rva - 0xc00)
  tobii_stream_supported             file 0x1404e0
  tobii_capability_supported         file 0x1406e0
  tobii_internal_stream_supported    file 0x149810
  tobii_internal_capability_supported file 0x149a10

Stubs
  x86: 8b 4c 24 0c            mov ecx, [esp+0x0c]   (3rd arg, __cdecl)
       c7 01 01 00 00 00      mov dword [ecx], 1
       33 c0                  xor eax, eax
       c3                     ret
  x64: 41 c7 00 01 00 00 00   mov dword [r8], 1     (3rd arg, Microsoft x64)
       31 c0                  xor eax, eax
       c3                     ret
  Both replace the prologue only and end in their own RET, so the original
  epilogue is never reached and the stack stays balanced.

Usage
  python make_patched_dlls.py            # regenerate repo artifacts only
  python make_patched_dlls.py --install  # also copy into the app install dir
"""

import hashlib
import os
import shutil
import sys

PRISTINE_X86 = r"C:\Users\xursc\Downloads\TobiiGhost_Extract\lib\native\x86\tobii_stream_engine.dll"
PRISTINE_X64 = r"C:\Users\xursc\Downloads\TobiiGhost_Extract\lib\native\x64\tobii_stream_engine.dll"

REPO = r"C:\Users\xursc\projects\tobii_playground"
APP = r"C:\Users\xursc\AppData\Local\TobiiGhost\app-1.14.1"

X86_STUB = bytes.fromhex("8b4c240cc7010100000033c0c3")          # 13 bytes
X86_CASE = bytes.fromhex("b0015f5ec3")                          # 5 bytes
X64_STUB = bytes.fromhex("41c7000100000031c0c3")                # 10 bytes

X86_SITES = [
    (0x11CA30, "tobii_stream_supported"),
    (0x11CB90, "tobii_capability_supported"),
    (0x1239B0, "tobii_internal_stream_supported"),
    (0x123B10, "tobii_internal_capability_supported"),
]
X86_CASE_SITE = (0x12D58C, "switch-case block (stream-supported dispatch)")

X64_SITES = [
    (0x1404E0, "tobii_stream_supported"),
    (0x1406E0, "tobii_capability_supported"),
    (0x149810, "tobii_internal_stream_supported"),
    (0x149A10, "tobii_internal_capability_supported"),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()[:16]


def patch_x86(pristine: bytes) -> bytes:
    data = bytearray(pristine)
    for off, name in X86_SITES:
        # the 13-byte stub replaces the original 13-byte prologue
        original = bytes(data[off:off + 13])
        if original == X86_STUB:
            continue
        if original[:1] != b"\x55":          # push ebp prologue
            raise SystemExit("[!] unexpected x86 prologue at 0x%x: %s" % (off, original.hex()))
        data[off:off + 13] = X86_STUB
        print("   x86 %-38s 0x%05x  %s -> force-true stub" % (name, off, original.hex()))
    off, name = X86_CASE_SITE
    original = bytes(data[off:off + 5])
    if original != X86_CASE:
        if original != bytes.fromhex("ba01000000"):
            raise SystemExit("[!] unexpected x86 case block at 0x%x: %s" % (off, original.hex()))
        data[off:off + 5] = X86_CASE
        print("   x86 %-38s 0x%05x  %s -> mov al,1 ; pop edi ; pop esi ; ret"
              % (name, off, original.hex()))
    if len(data) != len(pristine):
        raise SystemExit("[!] size changed")
    return bytes(data)


def patch_x64(pristine: bytes) -> bytes:
    data = bytearray(pristine)
    for off, name in X64_SITES:
        original = bytes(data[off:off + 10])
        if original == X64_STUB:
            continue
        # every target starts with a prologue (mov [rsp+..],reg / push / sub rsp)
        if original[:1] not in (b"\x48", b"\x40", b"\x41"):
            raise SystemExit("[!] unexpected x64 prologue at 0x%x: %s" % (off, original.hex()))
        data[off:off + 10] = X64_STUB
        print("   x64 %-38s 0x%05x  %s -> force-true stub" % (name, off, original.hex()))
    if len(data) != len(pristine):
        raise SystemExit("[!] size changed")
    return bytes(data)


def main():
    install = "--install" in sys.argv
    if not os.path.exists(PRISTINE_X86) or not os.path.exists(PRISTINE_X64):
        raise SystemExit("[!] pristine DLLs not found under %s" %
                         os.path.dirname(PRISTINE_X86))

    print("== x86 ==")
    x86 = patch_x86(open(PRISTINE_X86, "rb").read())
    out86 = os.path.join(REPO, "x86_patched_tobii_stream_engine.dll")
    open(out86, "wb").write(x86)
    print("   wrote %s (%d bytes, sha %s)" % (out86, len(x86), sha(x86)))

    print("== x64 ==")
    x64 = patch_x64(open(PRISTINE_X64, "rb").read())
    out64 = os.path.join(REPO, "x64_patched_tobii_stream_engine.dll")
    open(out64, "wb").write(x64)
    print("   wrote %s (%d bytes, sha %s)" % (out64, len(x64), sha(x64)))

    if install:
        for src, sub in ((out86, "x86"), (out64, "x64")):
            dst = os.path.join(APP, sub, "tobii_stream_engine.dll")
            if not os.path.exists(os.path.dirname(dst)):
                print("   SKIP %s (dir missing)" % dst)
                continue
            shutil.copy2(dst, dst + ".backup_premake")
            shutil.copy2(src, dst)
            print("   installed %s (sha %s)" % (dst, sha(open(dst, "rb").read())))
        # the app also keeps a copy at its root; keep it in sync
        root = os.path.join(APP, "tobii_stream_engine.dll")
        if os.path.exists(root):
            shutil.copy2(root, root + ".backup_premake")
            shutil.copy2(out86, root)
            print("   installed %s (sha %s)" % (root, sha(open(root, "rb").read())))

    print("done")


if __name__ == "__main__":
    main()
