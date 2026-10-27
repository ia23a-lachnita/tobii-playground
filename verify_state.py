#!/usr/bin/env python3
"""Read-only verification of the deployed patch state (no writes)."""
import hashlib
import os
import sys

SVC_INSTALLED = r"C:\Program Files\Tobii\Platform Runtime\platform_runtime_IS5LEYETRACKER5_service.exe"
SVC_REPO = r"C:\Users\xursc\projects\tobii_playground\platform_runtime_service.exe"
APP = r"C:\Users\xursc\AppData\Local\TobiiGhost\app-1.14.1"

PRIST_X86 = r"C:\Users\xursc\Downloads\TobiiGhost_Extract\lib\native\x86\tobii_stream_engine.dll"
PRIST_X64 = r"C:\Users\xursc\Downloads\TobiiGhost_Extract\lib\native\x64\tobii_stream_engine.dll"


def sha(p):
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
    except OSError as e:
        return "MISSING(%s)" % e.strerror


def rd(p):
    return open(p, "rb").read()


def show(d, off, n, label, expect=None):
    got = d[off:off + n].hex(" ")
    tag = ""
    if expect is not None:
        tag = "  OK" if got == expect.lower() else "  *** MISMATCH ***"
    print("   %-46s @0x%06x : %s%s" % (label, off, got, tag))


print("== service binary ==")
for label, p in (("installed", SVC_INSTALLED), ("repo", SVC_REPO)):
    if not os.path.exists(p):
        print(" %-10s MISSING" % label)
        continue
    d = rd(p)
    print(" %-10s sha %s  size %d" % (label, sha(p), len(d)))
    show(d, 0x264420, 10, "stream0 CMP slot (want 83 f8 00 ...)", "83 f8 00 0f 85 c8 00 00 00 33 d2")
    show(d, 0x26367D, 8, "ae34 HMD NOP (want 90 90 48 8d 15)", "90 90 48 8d 15")
    show(d, 0xE7B2C, 8, "PID gate imm32 (want 04 21 14 03)", "04 21 14 03")
    show(d, 0x2D2465, 8, "FW-check JMP (want eb 49 74 47)", "eb 49 74 47")
    show(d, 0x43E34C, 6, "PID log string (want '0x314')", "3078333134")
    for off in (0x26374F, 0x2637F0, 0x263891, 0x263932, 0x2639D3):
        show(d, off, 2, "identity jne @0x%x (want 90 90)" % off, "90 90")

print()
print("== client DLLs ==")
X86_STUB = bytes.fromhex("8b4c240cc7010100000033c0c3")
X86_CASE = bytes.fromhex("b0015f5ec3")
X64_STUB = bytes.fromhex("41c7000100000031c0c3")

x86_sites = [(0x11CA30, "tobii_stream_supported"),
              (0x11CB90, "tobii_capability_supported"),
              (0x1239B0, "tobii_internal_stream_supported"),
              (0x123B10, "tobii_internal_capability_supported")]
x64_sites = [(0x1404E0, "tobii_stream_supported"),
              (0x1406E0, "tobii_capability_supported"),
              (0x149810, "tobii_internal_stream_supported"),
              (0x149A10, "tobii_internal_capability_supported")]


def report(path, sites, stub, case_site=None, case=None):
    if not os.path.exists(path):
        print(" %s MISSING" % path)
        return
    d = rd(path)
    print(" %-72s sha %s size %d" % (path, sha(path), len(d)))
    for off, name in sites:
        show(d, off, len(stub), "  " + name, stub.hex(" "))
    if case_site is not None:
        show(d, case_site, len(case), "  case block", case.hex(" "))
    # x86 internal gate FUN_1012e170 (file 0x12d570) - entry bytes
    return d


for p in (os.path.join(APP, "x86", "tobii_stream_engine.dll"),
          os.path.join(APP, "tobii_stream_engine.dll"),
          r"C:\Users\xursc\projects\tobii_playground\x86_patched_tobii_stream_engine.dll"):
    d = report(p, x86_sites, X86_STUB, 0x12D58C, X86_CASE)
    if d:
        show(d, 0x12D570, 16, "  internal gate FUN_1012e170 entry")
        show(d, 0x12D58C, 20, "  internal gate case region")

for p in (os.path.join(APP, "x64", "tobii_stream_engine.dll"),
          r"C:\Users\xursc\projects\tobii_playground\x64_patched_tobii_stream_engine.dll"):
    report(p, x64_sites, X64_STUB)

print()
print("== pristine references ==")
for p in (PRIST_X86, PRIST_X64):
    print(" %-72s sha %s size %d" % (p, sha(p), os.path.getsize(p) if os.path.exists(p) else -1))

print()
print("== managed / helper DLLs in app dir ==")
for name in ("Tobii.Gaming.Tracking.Net.dll", "tobii_custom_log_t.dll", "middleware_client.dll"):
    for sub in ("", "x86", "x64"):
        p = os.path.join(APP, sub, name)
        if os.path.exists(p):
            print(" %-78s sha %s" % (p, sha(p)))
