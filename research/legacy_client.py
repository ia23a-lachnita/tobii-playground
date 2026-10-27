#!/usr/bin/env python3
"""Legacy NPS pipe client probe for the Tobii Platform Runtime service.

Maps the protocol observed in the service binary (FUN_1403ad100):
  1. client creates its own named pipe (everyone-access SD),
  2. connects to \\\\.\\pipe\\TOBII-<serial>,
  3. writes first packet: [u32 mode][ascii pipe-name]  (mode 1 = streaming),
  4. service dials back (CreateFile GENERIC_WRITE) into the client's pipe,
  5. whatever the service writes back is captured raw.

Frame log is plain hexdump text. No parsing yet — raw capture first.
"""

import ctypes
from ctypes import wintypes
import struct
import sys
import time

kernel32 = ctypes.windll.kernel32
advapi32 = ctypes.windll.advapi32

kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                 wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
kernel32.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.DWORD, wintypes.LPVOID]
kernel32.ConnectNamedPipe.restype = wintypes.BOOL
kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.ReadFile.restype = wintypes.BOOL
kernel32.ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                              ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
kernel32.WriteFile.restype = wintypes.BOOL
kernel32.WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.CancelIoEx.restype = wintypes.BOOL
kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.GetLastError.restype = wintypes.DWORD

advapi32 = None  # SDDL converter absent from this python build; use NULL SA

INVALID = ctypes.c_void_p(-1).value
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_MESSAGE = 0x00000004
PIPE_READMODE_MESSAGE = 0x00000002
PIPE_WAIT = 0x00000000

SERIAL = "IS510-100211404854"
MY_PIPE = "PRC-IS510-PROBE-0001"


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("nLength", wintypes.DWORD),
                ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", wintypes.BOOL)]


def everyone_sa():
    # NULL SA: pipe inherits the token's default DACL (user + SYSTEM).
    sa = SECURITY_ATTRIBUTES()
    sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
    sa.lpSecurityDescriptor = None
    sa.bInheritHandle = False
    return sa, None


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", wintypes.HANDLE), ("InternalHigh", wintypes.HANDLE),
                ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE)]


def hexdump(data, prefix=""):
    for i in range(0, min(len(data), 64 * 16), 16):
        chunk = data[i:i + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"{prefix}{i:04x}  {hexs:<47}  {asc}")


def main():
    sa, _sd = everyone_sa()
    mine = "\\\\.\\pipe\\" + MY_PIPE
    h_mine = kernel32.CreateNamedPipeW(
        mine, PIPE_ACCESS_DUPLEX, PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
        255, 65536, 65536, 5000, ctypes.byref(sa))
    if h_mine == INVALID or not h_mine:
        print(f"[!] CreateNamedPipe failed err={kernel32.GetLastError()}")
        return 1
    print(f"[ok] listening on {mine} (handle {h_mine})")

    # 2. connect to the service's legacy pipe (READ|WRITE)
    legacy = "\\\\.\\pipe\\TOBII-" + SERIAL
    h_srv = kernel32.CreateFileW(legacy, 0xC0000000, 0, None, OPEN_EXISTING, 0, None)
    if h_srv == INVALID or not h_srv:
        print(f"[!] legacy connect failed err={kernel32.GetLastError()}")
        kernel32.CloseHandle(h_mine)
        return 1
    print("[ok] connected to legacy service pipe")

    # 3. first packet: [mode=1][pipe-name]
    pkt = struct.pack("<I", 1) + MY_PIPE.encode() + b"\x00"
    written = wintypes.DWORD()
    ok = kernel32.WriteFile(h_srv, pkt, len(pkt), ctypes.byref(written), None)
    print(f"[i] wrote handshake {len(pkt)} bytes: ok={ok} written={written.value}")
    if not ok:
        print(f"[!] write err={kernel32.GetLastError()}")
        kernel32.CloseHandle(h_srv)
        kernel32.CloseHandle(h_mine)
        return 1

    # 4. wait for the service to dial back (ConnectNamedPipe is synchronous for
    #    blocking-mode pipes — this blocks until the service opens our end)
    print("[i] waiting for service to connect back...")
    ok = kernel32.ConnectNamedPipe(h_mine, None)
    err = kernel32.GetLastError()
    print(f"[i] ConnectNamedPipe ok={ok} err={err} (0=connected, 535=already)")

    # 5. send candidate streaming frames (TTP framings proven on direct USB),
    #    then capture whatever comes back. Service log distinguishes outcomes.
    HELLO47 = bytes([
        0x00, 0x00, 0x17, 0x00, 0x00, 0x00, 0x28, 0x00, 0x00, 0x00, 0x09,
        0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x01, 0x00,
        0x02, 0x00, 0x01, 0x00, 0x03, 0x00, 0x01, 0x00, 0x04, 0x00, 0x01,
        0x00, 0x05, 0x00, 0x01, 0x00, 0x06, 0x00, 0x01, 0x00, 0x07, 0x00,
        0x01, 0x00, 0x08])

    def env_frame(op, payload, seq):
        f = bytearray(32 + len(payload))
        f[0] = 0x00
        struct.pack_into("<I", f, 4, 24 + len(payload))
        f[8] = 0x51
        struct.pack_into(">I", f, 12, seq)
        struct.pack_into(">I", f, 20, op)
        struct.pack_into(">I", f, 28, len(payload))
        f[32:] = payload
        return bytes(f)

    frames = [
        ("HELLO envelope", env_frame(0x3E8, HELLO47, 1)),
        ("CAPS envelope", env_frame(0x546, b"", 2)),
        ("HELLO bare", env_frame(0x3E8, HELLO47, 1)[8:]),
    ]
    total = bytearray()
    for name, frame in frames:
        written = wintypes.DWORD()
        ok = kernel32.WriteFile(h_mine, frame, len(frame), ctypes.byref(written), None)
        print(f"[>] wrote {name} ({len(frame)} bytes): ok={ok} written={written.value}")
        # capture for 6s
        deadline = time.time() + 6
        while time.time() < deadline:
            buf = ctypes.create_string_buffer(65536)
            nread = wintypes.DWORD()
            ov = OVERLAPPED()
            ov.hEvent = kernel32.CreateEventW(None, True, False, None)
            ok = kernel32.ReadFile(h_mine, buf, len(buf), ctypes.byref(nread), ctypes.byref(ov))
            err = kernel32.GetLastError()
            if ok and nread.value:
                print(f"[<] reply to {name}: {nread.value} bytes")
                hexdump(buf.raw[:nread.value])
                total += buf.raw[:nread.value]
                kernel32.CloseHandle(ov.hEvent)
                continue
            if not ok and err == 997:
                w = kernel32.WaitForSingleObject(ov.hEvent, 1500)
                if w == 0 and kernel32.ReadFile(
                        h_mine, buf, len(buf), ctypes.byref(nread), ctypes.byref(ov)):
                    if nread.value:
                        print(f"[<] reply to {name}: {nread.value} bytes")
                        hexdump(buf.raw[:nread.value])
                        total += buf.raw[:nread.value]
                        kernel32.CloseHandle(ov.hEvent)
                        continue
                kernel32.CancelIoEx(h_mine, ctypes.byref(ov))
            kernel32.CloseHandle(ov.hEvent)
            if err == 109:
                break
            break
    print(f"[=] captured {len(total)} bytes total")
    kernel32.CloseHandle(h_mine)
    kernel32.CloseHandle(h_srv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
