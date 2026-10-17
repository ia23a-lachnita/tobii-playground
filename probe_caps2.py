#!/usr/bin/env python3
"""Probe the Tobii 5L's capability list over direct USB — protocol-corrected.

v1 learned: discovery/WinUSB plumbing works (fixed 64-bit ctypes signatures),
but the device never answered. Root cause: wrong wire protocol. This version
replicates the byte-exact framing of the WORKING reference demo
(TobiiGazeDemo/Program.cs, which streamed gaze at ~0.25 deg):

1. Session open: vendor control transfer RequestType=0x41 Request=0x41
   BEFORE any bulk I/O (v1 skipped this — device silently discards frames).
2. Transport frame (32+ bytes):
     [0x00][pad 3][envelope_len LE u32 @4 = 24+payload_len]
     [0x51 magic @8][pad 3]
     [seq BE u32 @12][X @16][op BE u32 @20][Y @24][payload_len BE u32 @28]
     [payload @32]
   (v1 used a 16-byte header with the wrong field order.)
3. HELLO op 0x3e8 carries the demo's stream-id list (ids 0x0001..0x0008).

Then GET_CAPABILITIES (op 0x546, the service's own query op) is sent with
several payload variants and every response is hexdumped: that dump shows the
raw capability list — the exact stream ids the 5L reports and their values.

Run with the service STOPPED (it owns the USB device):
    net stop TobiiPlatformRuntime
    python probe_caps2.py
    net start TobiiPlatformRuntime
"""

import ctypes
from ctypes import wintypes, Structure, POINTER, byref
import struct
import sys
import time

winusb = ctypes.windll.winusb
kernel32 = ctypes.windll.kernel32
setupapi = ctypes.windll.setupapi


class GUID(Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_byte * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", POINTER(ctypes.c_ulong)),
    ]


class OVERLAPPED(Structure):
    _fields_ = [
        ("Internal", POINTER(ctypes.c_ulong)),
        ("InternalHigh", POINTER(ctypes.c_ulong)),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


class WINUSB_SETUP_PACKET(Structure):
    _fields_ = [
        ("RequestType", ctypes.c_ubyte),
        ("Request", ctypes.c_ubyte),
        ("Value", wintypes.USHORT),
        ("Index", wintypes.USHORT),
        ("Length", wintypes.USHORT),
    ]


setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
setupapi.SetupDiGetClassDevsW.argtypes = [
    POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD,
]
setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, POINTER(GUID), wintypes.DWORD,
    ctypes.c_void_p,
]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wintypes.HANDLE, POINTER(SP_DEVICE_INTERFACE_DATA), wintypes.LPVOID,
    wintypes.DWORD, POINTER(wintypes.DWORD), wintypes.LPVOID,
]
setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]

kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = [
    wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR,
]

winusb.WinUsb_Initialize.restype = wintypes.BOOL
winusb.WinUsb_Initialize.argtypes = [wintypes.HANDLE, POINTER(wintypes.HANDLE)]
winusb.WinUsb_Free.restype = wintypes.BOOL
winusb.WinUsb_Free.argtypes = [wintypes.HANDLE]
winusb.WinUsb_ControlTransfer.restype = wintypes.BOOL
winusb.WinUsb_ControlTransfer.argtypes = [
    wintypes.HANDLE, WINUSB_SETUP_PACKET, wintypes.LPVOID, wintypes.ULONG,
    POINTER(wintypes.ULONG), wintypes.LPVOID,
]
winusb.WinUsb_WritePipe.restype = wintypes.BOOL
winusb.WinUsb_WritePipe.argtypes = [
    wintypes.HANDLE, ctypes.c_ubyte, ctypes.c_void_p, wintypes.ULONG,
    POINTER(wintypes.ULONG), wintypes.LPVOID,
]
winusb.WinUsb_ReadPipe.restype = wintypes.BOOL
winusb.WinUsb_ReadPipe.argtypes = [
    wintypes.HANDLE, ctypes.c_ubyte, ctypes.c_void_p, wintypes.ULONG,
    POINTER(wintypes.ULONG), wintypes.LPVOID,
]
winusb.WinUsb_GetOverlappedResult.restype = wintypes.BOOL
winusb.WinUsb_GetOverlappedResult.argtypes = [
    wintypes.HANDLE, wintypes.LPVOID, POINTER(wintypes.ULONG), wintypes.BOOL,
]
winusb.WinUsb_AbortPipe.restype = wintypes.BOOL
winusb.WinUsb_AbortPipe.argtypes = [wintypes.HANDLE, ctypes.c_ubyte]

INVALID_HANDLE_VALUE = -1
ERROR_IO_PENDING = 997
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_FLAG_OVERLAPPED = 0x40000000
DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000

EP_BULK_IN = 0x83
EP_BULK_OUT = 0x05

OP_HELLO = 0x3E8
OP_QUERY_REALM = 0x640
OP_GET_CAPABILITIES = 0x546
OP_GET_CAPABILITIES_ALL = 0x547

# HELLO payload, byte-exact from the working demo (stream ids 0x0001-0x0008)
HELLO_PAYLOAD = bytes([
    0x00, 0x00, 0x17, 0x00, 0x00, 0x00, 0x28, 0x00, 0x00, 0x00, 0x09,
    0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x01, 0x00,
    0x02, 0x00, 0x01, 0x00, 0x03, 0x00, 0x01, 0x00, 0x04, 0x00, 0x01,
    0x00, 0x05, 0x00, 0x01, 0x00, 0x06, 0x00, 0x01, 0x00, 0x07, 0x00,
    0x01, 0x00, 0x08])


def _parse_guid(s):
    parts = s.strip("{}").split("-")
    g = GUID()
    g.Data1 = int(parts[0], 16)
    g.Data2 = int(parts[1], 16)
    g.Data3 = int(parts[2], 16)
    g.Data4 = (ctypes.c_byte * 8)(*bytes.fromhex(parts[3] + parts[4]))
    return g


def find_device():
    GUIDS_TO_TRY = (
        "{85C0F97C-E2B1-422A-92A9-5F96072E79D8}",
        "{A5DCBF10-6530-11D2-901F-00C04FB951ED}",
        "{88BAE032-5A81-49F0-BC3D-A4FF138216D6}",
    )
    found, seen = None, []
    for guid_str in GUIDS_TO_TRY:
        guid = _parse_guid(guid_str)
        dev_info = setupapi.SetupDiGetClassDevsW(
            byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
        )
        if not dev_info or dev_info == INVALID_HANDLE_VALUE:
            continue
        interface_data = SP_DEVICE_INTERFACE_DATA()
        interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
        idx = 0
        while setupapi.SetupDiEnumDeviceInterfaces(
            dev_info, None, byref(guid), idx, byref(interface_data)
        ):
            required_size = wintypes.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info, byref(interface_data), None, 0,
                byref(required_size), None,
            )
            n = max(required_size.value, 512)
            buf = ctypes.create_unicode_buffer(n // 2 + 8)
            ctypes.cast(buf, POINTER(wintypes.DWORD))[0] = 8
            if setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info, byref(interface_data), buf, n,
                byref(required_size), None,
            ):
                path = buf[2:].split("\x00", 1)[0]
                if path not in seen:
                    seen.append(path)
                low = path.lower()
                if "vid_2104" in low and ("pid_0314" in low or "pid_0313" in low):
                    if "winusb" in low or "mi_00" in low or guid_str.startswith("{85C0F97C"):
                        found = path
                    elif found is None:
                        found = path
            idx += 1
        setupapi.SetupDiDestroyDeviceInfoList(dev_info)
    if found:
        print(f"[ok] device interface: {found}")
        return found
    print(f"[!] no VID_2104 interface found ({len(seen)} scanned)")
    return None


class Probe:
    def __init__(self, path):
        self.handle = None
        self.winusb_handle = None
        self.seq = 0
        self.path = path
        self.events = []

    def open(self):
        self.handle = kernel32.CreateFileW(
            self.path, GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OVERLAPPED, None,
        )
        err = kernel32.GetLastError()
        if (not self.handle or self.handle == INVALID_HANDLE_VALUE
                or self.handle == 0xFFFFFFFFFFFFFFFF):
            print(f"[!] CreateFile failed: error {err} (5 = access denied: "
                  f"stop the service first!)")
            return False
        self.winusb_handle = wintypes.HANDLE()
        if not winusb.WinUsb_Initialize(self.handle, byref(self.winusb_handle)):
            print(f"[!] WinUsb_Initialize failed: error {kernel32.GetLastError()}")
            return False
        print("[ok] WinUSB interface open")
        return True

    def close(self):
        if self.winusb_handle:
            winusb.WinUsb_Free(self.winusb_handle)
        if self.handle:
            kernel32.CloseHandle(self.handle)
        for ev in self.events:
            kernel32.CloseHandle(ev)
        self.events.clear()

    def session_open(self):
        """Vendor control transfer 0x41/0x41 — required before bulk I/O."""
        pkt = WINUSB_SETUP_PACKET(RequestType=0x41, Request=0x41)
        xfer = wintypes.ULONG()
        ok = winusb.WinUsb_ControlTransfer(
            self.winusb_handle, pkt, None, 0, byref(xfer), None
        )
        print(f"[i] session open (ctrl 0x41/0x41): ok={ok} "
              f"err={kernel32.GetLastError()}")
        return ok

    def session_close(self):
        pkt = WINUSB_SETUP_PACKET(RequestType=0x41, Request=0x42)
        xfer = wintypes.ULONG()
        winusb.WinUsb_ControlTransfer(
            self.winusb_handle, pkt, None, 0, byref(xfer), None
        )

    def _overlapped(self):
        ov = OVERLAPPED()
        ov.hEvent = kernel32.CreateEventW(None, True, False, None)
        self.events.append(ov.hEvent)
        return ov

    def send(self, opcode, payload=b""):
        """24-byte TTP header per the working demo: magic@0(+3 pad),
        seq@4, X@8, op@12, Y@16, payload_len@20, payload@24; wrapped in
        [0x00][pad3][env_len LE = 24+len]."""
        self.seq += 1
        frame = bytearray(8 + 24 + len(payload))
        frame[0] = 0x00
        struct.pack_into("<I", frame, 4, 24 + len(payload))
        frame[8] = 0x51
        struct.pack_into(">I", frame, 12, self.seq)
        struct.pack_into(">I", frame, 20, opcode)
        struct.pack_into(">I", frame, 28, len(payload))
        frame[32:] = payload
        buf = ctypes.create_string_buffer(bytes(frame))
        written = wintypes.ULONG()
        ov = self._overlapped()
        ok = winusb.WinUsb_WritePipe(
            self.winusb_handle, EP_BULK_OUT, buf, len(frame),
            byref(written), byref(ov),
        )
        if not ok and kernel32.GetLastError() != ERROR_IO_PENDING:
            print(f"[!] write failed: error {kernel32.GetLastError()}")
            return False
        if not ok:
            kernel32.WaitForSingleObject(ov.hEvent, 5000)
            if not winusb.WinUsb_GetOverlappedResult(
                self.winusb_handle, byref(ov), byref(written), False
            ):
                print("[!] write overlapped failed")
                return False
        return True

    def read(self, timeout_ms=500):
        buf = ctypes.create_string_buffer(16384)
        nread = wintypes.ULONG()
        ov = self._overlapped()
        ok = winusb.WinUsb_ReadPipe(
            self.winusb_handle, EP_BULK_IN, buf, len(buf),
            byref(nread), byref(ov),
        )
        if not ok:
            if kernel32.GetLastError() == ERROR_IO_PENDING:
                rc = kernel32.WaitForSingleObject(ov.hEvent, timeout_ms)
                if rc != 0:
                    winusb.WinUsb_AbortPipe(self.winusb_handle, EP_BULK_IN)
                    return None
                if not winusb.WinUsb_GetOverlappedResult(
                    self.winusb_handle, byref(ov), byref(nread), False
                ):
                    return None
            else:
                return None
        return buf.raw[: nread.value]


def parse_frames(data):
    """Walk IN transport frames: magic 0x52/0x53 at byte 8, op BE u32 @20,
    payload_len BE u32 @28, payload @32; next frame at 8 + envelope_len."""
    frames = []
    off = 0
    while off + 40 <= len(data) + 8:
        if off + 32 > len(data):
            break
        magic = data[off + 8]
        op = plen = None
        if off + 32 <= len(data):
            op = struct.unpack(">I", data[off + 20:off + 24])[0]
            plen = struct.unpack(">I", data[off + 28:off + 32])[0]
        env = struct.unpack("<I", data[off + 4:off + 8])[0] if off + 8 <= len(data) else 0
        if magic in (0x52, 0x53) and plen is not None:
            payload = data[off + 32: off + 32 + plen]
            frames.append((magic, op, plen, payload))
            step = 8 + env if 24 + plen == env or env else 8 + 24 + plen
            off += max(step, 8)
        else:
            frames.append((magic, op, plen, data[off + 32:]))
            break
    return frames


def hexdump(data, base=0, limit=768):
    out = []
    for off in range(0, min(len(data), limit), 16):
        chunk = data[off:off + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        ascii_ = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"  {base + off:04x}  {hexs:<47}  {ascii_}")
    return "\n".join(out)


def parse_caps_entries(payload):
    """Candidate 0x7c-stride entries: u32 id at +0, 5-byte value at +4.
    The value is the NUL-terminated 5-byte string the service compares
    against "true" (DAT_14112ea88 = 74 72 75 65 00)."""
    results = []
    good = (b"true", b"false", b"true\x00", b"false\x00")
    # id+value only needs 9 bytes — the full 0x7c stride holds other fields,
    # so scan to the end (minus 9), not to (len - 0x7c).
    for start in range(0, max(len(payload) - 8, 1), 4):
        cid = struct.unpack(">I", payload[start:start + 4])[0]
        val = payload[start + 4:start + 9]
        if cid <= 0x40 and val in good:
            results.append((start, cid, val))
    return results


def drain(p, seconds=0.8, label=""):
    """Read the IN pipe for N seconds, parse frames, print them."""
    end = time.time() + seconds
    all_data = bytearray()
    while time.time() < end:
        d = p.read(200)
        if not d:
            time.sleep(0.05)
            continue
        all_data += d
    if not all_data:
        print(f"    {label}(no data)")
        return None
    print(f"    {label}{len(all_data)} bytes")
    frames = parse_frames(bytes(all_data))
    for magic, op, plen, payload in frames:
        tag = {0x51: "REQ", 0x52: "RSP", 0x53: "NOTE"}.get(magic, f"?0x{magic:x}")
        print(f"    <- {tag} op=0x{op if op is None else op:x} plen={plen}")
        if payload:
            print(hexdump(payload[:768]))
            if len(payload) > 768:
                print(f"    ... ({len(payload) - 768} more bytes)")
    return bytes(all_data)


def main():
    print("[i] looking for Tobii device (VID 2104, PID 0314/0313)...")
    path = find_device()
    if not path:
        print("[!] device not found (plugged in? service stopped?)")
        return 1

    p = Probe(path)
    if not p.open():
        return 1

    try:
        if not p.session_open():
            print("[!] session open failed — aborting")
            return 1

        print("[i] HELLO (op 0x3e8, demo stream list)...")
        p.send(OP_HELLO, HELLO_PAYLOAD)
        hello = drain(p, 1.0, "hello: ")

        print("[i] QUERY_REALM (op 0x640)...")
        p.send(OP_QUERY_REALM, b"\x00\x00")
        drain(p, 0.8, "realm: ")

        # GET_CAPABILITIES variants — dump everything that comes back
        variants = [
            (OP_GET_CAPABILITIES, b"\x00\x00", "caps 0x546 [00 00]"),
            (OP_GET_CAPABILITIES, b"", "caps 0x546 [empty]"),
            (OP_GET_CAPABILITIES_ALL, b"\x00\x00", "caps_all 0x547 [00 00]"),
            (OP_GET_CAPABILITIES_ALL, b"", "caps_all 0x547 [empty]"),
        ]
        for op, payload, label in variants:
            print(f"[i] {label}...")
            p.send(op, payload)
            resp = drain(p, 1.0, f"{label}: ")
            if resp:
                entries = parse_caps_entries(resp)
                if entries:
                    print(f"    [i] {len(entries)} candidate entries "
                          f"(offset, id, value):")
                    for start, cid, val in entries:
                        print(f"      +0x{start:04x}: id={cid} (0x{cid:x}) "
                              f"value={val!r}")
    finally:
        p.session_close()
        p.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
