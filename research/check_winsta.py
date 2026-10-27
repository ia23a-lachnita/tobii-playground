import ctypes
import os

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32

session_id = ctypes.c_uint32()
kernel32.ProcessIdToSessionId(kernel32.GetCurrentProcessId(), ctypes.byref(session_id))
print("Process Session ID:", session_id.value)

hwinsta = user32.GetProcessWindowStation()
buf = ctypes.create_unicode_buffer(256)
user32.GetUserObjectInformationW(hwinsta, 2, buf, 512, None)
print("WindowStation name:", buf.value)
