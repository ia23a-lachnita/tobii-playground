import ctypes
from ctypes import wintypes

kernel32 = ctypes.windll.kernel32
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
INVALID = ctypes.c_void_p(-1).value
pipe = "\\\\.\\pipe\\TOBiiPRP-IS510-100211404854"
for mask, name in [(0x80000000, "GENERIC_READ"), (0x40000000, "GENERIC_WRITE"),
                   (0xC0000000, "READ|WRITE"), (0x10000000, "EXECUTE_ALONE")]:
    h = kernel32.CreateFileW(pipe, mask, 3, None, 3, 0, None)
    err = kernel32.GetLastError()
    ok = bool(h) and h != INVALID and h != 0xFFFFFFFFFFFFFFFF
    print(f"{name:>14} -> {'CONNECTED' if ok else 'denied err=%d' % err}")
    if ok:
        kernel32.CloseHandle(h)
