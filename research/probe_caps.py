#!/usr/bin/env python3
"""Probe the Tobii 5L's raw capability list over direct USB (WinUSB/TTP).

WHY: The installed Platform Runtime service (patched to accept PID 0x0314)
enumerates the device-reported stream ids, and stream id 0 hits the
"Found unmapped stream 0" branch in stream_type_receiver
(platmod_castor_setup_capabilities.cpp). The service's TTP query for the
capability list is op 0x546 (from request builder FUN_1402c5bd0:
MOV dword [RSP+0x20], 0x546) and per-entry values are compared against the
5-byte string "true" (DAT_14112ea88), entries 0x7c bytes apart.

This probe sends the SAME query the service sends and dumps the raw
response so we can see, byte-for-byte, what the 5L reports:
  - the stream id encoding (small int 0..13? or 16-bit 0x0500-style?)
  - which ids it lists and their "true"/"false" values

Run with the Platform Runtime service STOPPED (it owns the USB device):
    net stop TobiiPlatformRuntime
    python probe_caps.py
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

# --- Struct + signature declarations. WITHOUT explicit restypes/argtypes,
# --- ctypes marshals HANDLEs as 32-bit ints on x64: SetupDiGetClassDevsW's
# --- return is truncated, every subsequent SetupAPI call fails silently,
# --- and enumeration yields nothing. This was the "device not found" bug.


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


setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
setupapi.SetupDiGetClassDevsW.argtypes = [
    POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD,
]
# NOTE: SetupDiEnumDeviceInterfaces takes FIVE params:
# (DeviceInfoSet, DeviceInfoData=NULL, InterfaceClassGuid, MemberIndex,
#  out DeviceInterfaceData). Dropping the NULL slot breaks the call.
setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, POINTER(GUID), wintypes.DWORD,
    ctypes.c_void_p,
]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wintypes.HANDLE, wintypes.LPVOID, wintypes.LPVOID,
    wintypes.DWORD, POINTER(wintypes.DWORD), wintypes.LPVOID,
]

# SP_DEVICE_INTERFACE_DATA on x64 = DWORD cbSize + GUID(16) + DWORD Flags +
# ULONG_PTR Reserved = 32 bytes (verified: ctypes.sizeof == 32, and an
# enum call with cbSize=32 succeeds — 40 in cbSize makes the API reject
# the struct with ERROR_INVALID_PARAMETER 87).
SP_DEVICE_INTERFACE_DATA_SIZE = 32


def _make_interface_data():
    buf = ctypes.create_string_buffer(SP_DEVICE_INTERFACE_DATA_SIZE)
    ctypes.cast(buf, POINTER(wintypes.DWORD))[0] = SP_DEVICE_INTERFACE_DATA_SIZE
    return buf


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

TRANSPORT_TYPE_COMMAND = 1

OP_HELLO = 0x3E8
OP_GET_CAPABILITIES = 0x546
OP_GET_CAPABILITIES_ALL = 0x547  # candidate op for the "_all" variant (verify)

TTP_MAGIC = b"true"


def _parse_guid(s):
    parts = s.strip("{}").split("-")
    g = GUID()
    g.Data1 = int(parts[0], 16)
    g.Data2 = int(parts[1], 16)
    g.Data3 = int(parts[2], 16)
    g.Data4 = (ctypes.c_byte * 8)(*bytes.fromhex(parts[3] + parts[4]))
    return g


def find_device():
    # The device's WinUSB interface GUID (MI_00, verified via earlier
    # streaming) first, then the generic USB device GUIDs as fallback.
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

        interface_data = _make_interface_data()

        idx = 0
        while setupapi.SetupDiEnumDeviceInterfaces(
            dev_info, None, byref(guid), idx, byref(interface_data)
        ):
            required_size = wintypes.DWORD()
            # size query: NULL buffer -> required_size holds needed bytes
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info, byref(interface_data), None, 0,
                byref(required_size), None,
            )
            n = max(required_size.value, 512)
            buf = ctypes.create_unicode_buffer(n // 2 + 8)
            # SP_DEVICE_INTERFACE_DETAIL_DATA_W native x64 layout: DWORD cbSize
            # + 4 bytes padding, then the WCHAR path. Set cbSize = 8.
            ctypes.cast(buf, POINTER(wintypes.DWORD))[0] = 8
            ok = setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info, byref(interface_data), buf, n,
                byref(required_size), None,
            )
            if ok:
                # Layout proven empirically: cbSize DWORD at bytes 0-3, then
                # the WCHAR path at byte 4 (wchar index 2) — no padding, even
                # though sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W)=8 on x64.
                # Cut at the NUL terminator.
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

    print(f"[!] no VID_2104 interface path found ({len(seen)} interfaces scanned):")
    for p in seen[:40]:
        print(f"    {p}")
    return None


class Probe:
    def __init__(self, path):
        self.handle = None
        self.winusb_handle = None
        self.seq = 1
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
        # HANDLE restype can surface as -1 or as the raw unsigned 64-bit
        # INVALID_HANDLE_VALUE (0xFFFFFFFFFFFFFFFF); check both forms.
        if (not self.handle or self.handle == INVALID_HANDLE_VALUE
                or self.handle == 0xFFFFFFFFFFFFFFFF):
            print(f"[!] CreateFile failed: error {err} "
                  f"(5 = access denied: stop the service first!)")
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

    def send(self, opcode, data=b""):
        """TTP request: 16-byte BE header (op, seq, status, object) + data,
        wrapped in a transport frame."""
        payload = struct.pack(">IIII", opcode, self.seq, 0, 0) + data
        frame = struct.pack("<II", TRANSPORT_TYPE_COMMAND, len(payload)) + payload
        self.seq += 1

        written = wintypes.DWORD()
        ov = self._new_overlapped()
        ok = winusb.WinUsb_WritePipe(
            self.winusb_handle, EP_BULK_OUT, frame, len(frame),
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

    def read(self, timeout_ms=400):
        buf = ctypes.create_string_buffer(16384)
        read = wintypes.DWORD()
        ov = self._new_overlapped()
        ok = winusb.WinUsb_ReadPipe(
            self.winusb_handle, EP_BULK_IN, buf, len(buf), byref(read), byref(ov)
        )
        if not ok:
            err = kernel32.GetLastError()
            if err == ERROR_IO_PENDING:
                rc = kernel32.WaitForSingleObject(ov.hEvent, timeout_ms)
                if rc != 0:  # WAIT_OBJECT_0
                    winusb.WinUsb_AbortPipe(self.winusb_handle, EP_BULK_IN)
                    return None
                if not winusb.WinUsb_GetOverlappedResult(
                    self.winusb_handle, byref(ov), byref(read), False
                ):
                    return None
            else:
                return None
        return buf.raw[: read.value]

    def _new_overlapped(self):
        o = OVERLAPPED()
        o.hEvent = kernel32.CreateEventW(None, True, False, None)
        self.events.append(o.hEvent)
        return o


def hexdump(data, base=0):
    out = []
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        ascii_ = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"  {base + off:04x}  {hexs:<47}  {ascii_}")
    return "\n".join(out)


def parse_frames(data):
    """Walk transport frames in a raw bulk-IN read buffer."""
    frames = []
    off = 0
    while off + 8 <= len(data):
        ftype, plen = struct.unpack("<II", data[off:off + 8])
        if plen + off + 8 > len(data):
            frames.append((ftype, data[off + 8:]))
            break
        frames.append((ftype, data[off + 8: off + 8 + plen]))
        off += 8 + plen
    return frames


def parse_caps_entries(payload):
    """Try to find 0x7c-stride entries: u32 id at +0, 5-byte value at +4."""
    results = []
    n = len(payload)
    for start in range(0, n - 0x7c, 4):
        cid = struct.unpack(">I", payload[start:start + 4])[0]
        val = payload[start + 4:start + 9]
        if cid <= 0x40 and val in (TTP_MAGIC, b"false"):
            results.append((start, cid, val))
    return results


def main():
    print("[i] looking for Tobii device (VID 2104, PID 0314/0313)...")
    path = find_device()
    if not path:
        print("[!] device not found (is it plugged in? is the service stopped?)")
        return 1

    p = Probe(path)
    if not p.open():
        return 1

    try:
        # 1) hello (the service/demo does this first to open a session)
        print("[i] sending HELLO (op 0x3e8)...")
        p.send(OP_HELLO)
        time.sleep(0.3)
        for _ in range(3):
            d = p.read(200)
            if not d:
                break
            for ftype, payload in parse_frames(d):
                if len(payload) >= 16:
                    op, seq, status, obj = struct.unpack(">IIII", payload[:16])
                    print(f"    <- ftype={ftype} op=0x{op:x} seq={seq} "
                          f"status=0x{status:x} obj=0x{obj:x} len={len(payload)}")

        # 2) capabilities query (the query stream_type_receiver dispatches on)
        for op in (OP_GET_CAPABILITIES, OP_GET_CAPABILITIES_ALL):
            print(f"[i] sending GET_CAPABILITIES op 0x{op:x}...")
            p.send(op)
            time.sleep(0.4)

            collected = bytearray()
            for _ in range(40):
                d = p.read(250)
                if not d:
                    break
                collected += d
                for ftype, payload in parse_frames(d):
                    if len(payload) >= 16:
                        hop, hseq, hstatus, hobj = struct.unpack(">IIII", payload[:16])
                        if hstatus != 0 or len(payload) > 16:
                            print(f"    <- op=0x{hop:x} seq={hseq} status=0x{hstatus:x} "
                                  f"obj=0x{hobj:x} payload_len={len(payload)}")

            if not collected:
                print("    (no response)")
                continue

            print(f"[i] op 0x{op:x}: collected {len(collected)} bytes")
            print(hexdump(collected[:512]))
            if len(collected) > 512:
                print(f"    ... ({len(collected) - 512} more bytes)")

            entries = parse_caps_entries(collected)
            if entries:
                print(f"[i] parsed {len(entries)} candidate entries (offset, id, value):")
                for start, cid, val in entries:
                    print(f"    +0x{start:04x}: id={cid} (0x{cid:x}) value={val!r}")
            else:
                print("[i] no 0x7c-stride entries found in this response")
            print()

    finally:
        p.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
