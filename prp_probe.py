#!/usr/bin/env python3
"""Probe what the Tobii Platform Runtime service serves to PRP clients.

The service listens on \\\\.\\pipe\\TOBIIPRP-<serial>. Ghost (Tobii Gaming SDK)
connects, reads capabilities, and decides 'eyetracking' support at connect time.
This probe connects as a client and dumps everything, so we see the EXACT
capability payload the service hands out post-patch.

Tries both framing variants seen in RE:
  A) 32-byte USB envelope ([0x00][pad3][env_len LE][0x51][pad3]..) wrapping
     the 24-byte TTP header (op BE @20, plen BE @28, seq BE @12)
  B) bare 24-byte TTP header + payload
Reads server-first bytes, then sends HELLO (0x3e8) and dumps the answer.

Usage: python prp_probe.py [pipe-suffix]
"""

import ctypes
from ctypes import wintypes
import struct
import sys

kernel32 = ctypes.windll.kernel32

kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                 wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                 wintypes.HANDLE]
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
kernel32.SetNamedPipeHandleState.restype = wintypes.BOOL
kernel32.SetNamedPipeHandleState.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD),
                                             ctypes.POINTER(wintypes.DWORD),
                                             ctypes.POINTER(wintypes.DWORD)]
kernel32.WaitNamedPipeW.restype = wintypes.BOOL
kernel32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
PIPE_READMODE_BYTE = 0x00000000

HELLO_PAYLOAD = bytes([
    0x00, 0x00, 0x17, 0x00, 0x00, 0x00, 0x28, 0x00, 0x00, 0x00, 0x09,
    0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x01, 0x00,
    0x02, 0x00, 0x01, 0x00, 0x03, 0x00, 0x01, 0x00, 0x04, 0x00, 0x01,
    0x00, 0x05, 0x00, 0x01, 0x00, 0x06, 0x00, 0x01, 0x00, 0x07, 0x00,
    0x01, 0x00, 0x08])


def hexdump(data, maxrows=16):
    for i in range(0, min(len(data), maxrows * 16), 16):
        chunk = data[i:i + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print("   %04x  %-47s  %s" % (i, hexs, asc))


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", wintypes.HANDLE), ("InternalHigh", wintypes.HANDLE),
                ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE)]


class PipeProbe:
    def __init__(self, name):
        self.name = name
        self.h = None
        self.events = []

    def _ov(self):
        ov = OVERLAPPED()
        ov.hEvent = kernel32.CreateEventW(None, True, False, None)
        self.events.append(ov.hEvent)
        return ov

    def open(self):
        path = "\\\\.\\pipe\\" + self.name
        self.h = kernel32.CreateFileW(
            path, 0x80000000 | 0x40000000, FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
        err = kernel32.GetLastError()
        if not self.h or self.h == INVALID_HANDLE_VALUE:
            print(f"[!] CreateFile {path} failed err={err}")
            return False
        mode = wintypes.DWORD(PIPE_READMODE_BYTE)
        kernel32.SetNamedPipeHandleState(self.h, ctypes.byref(mode), None, None)
        print(f"[ok] {path} connected (handle {self.h})")
        return True

    def close(self):
        if self.h:
            kernel32.CloseHandle(self.h)
        for ev in self.events:
            kernel32.CloseHandle(ev)
        self.events.clear()

    def read_any(self, timeout_ms=3000, total_cap=65536):
        """Read until quiet-timeout or cap; returns all bytes received."""
        out = b""
        deadline_reads = 3
        while len(out) < total_cap and deadline_reads > 0:
            deadline_reads -= 1
            buf = ctypes.create_string_buffer(8192)
            nread = wintypes.DWORD(0)
            ov = self._ov()
            ok = kernel32.ReadFile(self.h, buf, len(buf), ctypes.byref(nread),
                                   ctypes.byref(ov))
            err = kernel32.GetLastError()
            if ok and nread.value:
                out += buf.raw[:nread.value]
                continue
            if not ok and err == 997:  # ERROR_IO_PENDING
                w = kernel32.WaitForSingleObject(ov.hEvent, timeout_ms)
                if w == 0:  # WAIT_OBJECT_0
                    if kernel32.ReadFile(self.h, buf, len(buf),
                                         ctypes.byref(nread), ctypes.byref(ov)):
                        if nread.value:
                            out += buf.raw[:nread.value]
                            continue
                    if kernel32.GetLastError() in (109, 234):  # broken pipe
                        break
                    continue
                kernel32.CancelIoEx(self.h, ctypes.byref(ov))
                if not out:
                    continue
                break
            if not ok and err == 109:  # ERROR_BROKEN_PIPE
                break
            break
        return out

    def write(self, data):
        buf = ctypes.create_string_buffer(bytes(data))
        written = wintypes.DWORD(0)
        ov = self._ov()
        ok = kernel32.WriteFile(self.h, buf, len(data), ctypes.byref(written),
                                ctypes.byref(ov))
        err = kernel32.GetLastError()
        if not ok and err == 997:
            kernel32.WaitForSingleObject(ov.hEvent, 5000)
            ok = True
        if not ok:
            print(f"[!] write failed err={err}")
            return False
        return written.value == len(data)


def ttp_frame(op, payload=b"", seq=1, envelope=True):
    """Envelope variant mirrors the working USB probe byte-exactly:
    [0x00][pad3][env_len LE @4][0x51 @8][pad3][seq BE @12][X @16]
    [op BE @20][Y @24][plen BE @28][payload @32].
    Bare variant: plain 24-byte TTP header + payload."""
    if envelope:
        # 32-byte envelope: seq @12, op @20, plen @28, payload @32
        f = bytearray(32 + len(payload))
        f[0] = 0x00
        struct.pack_into("<I", f, 4, 24 + len(payload))
        f[8] = 0x51
        seq_off, op_off, plen_off, pay_off = 12, 20, 28, 32
    else:
        # bare 24-byte TTP header: seq @0, op @8, plen @16, payload @24
        f = bytearray(24 + len(payload))
        seq_off, op_off, plen_off, pay_off = 0, 8, 16, 24
    struct.pack_into(">I", f, seq_off, seq)
    struct.pack_into(">I", f, op_off, op)
    struct.pack_into(">I", f, plen_off, len(payload))
    f[pay_off:] = payload
    return bytes(f)


def attempt(pipe, envelope, label):
    print(f"\n--- {label} ({pipe}, envelope={envelope}) ---")
    p = PipeProbe(pipe)
    if not p.open():
        return
    initial = p.read_any(2500)
    print(f"[i] server-first: {len(initial)} bytes")
    hexdump(initial)
    frame = ttp_frame(0x3E8, HELLO_PAYLOAD, envelope=envelope)
    print(f"[i] send HELLO ({len(frame)} bytes)")
    if p.write(frame):
        ans = p.read_any(3000)
        print(f"[<] answer: {len(ans)} bytes")
        hexdump(ans, maxrows=40)
    p.close()


if __name__ == "__main__":
    serial = "IS510-100211404854"
    pipe = sys.argv[1] if len(sys.argv) > 1 else f"TOBIIPRP-{serial}"
    for envelope in (True, False):
        attempt(pipe, envelope, "variant")
