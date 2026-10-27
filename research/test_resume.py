import ctypes
import os

DLL_PATH = os.path.abspath("x64_patched_tobii_stream_engine.dll")
dll = ctypes.CDLL(DLL_PATH)

dll.tobii_api_create.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_void_p]
dll.tobii_api_create.restype = ctypes.c_int
dll.tobii_device_create.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
dll.tobii_device_create.restype = ctypes.c_int
dll.tobii_resume_device.argtypes = [ctypes.c_void_p]
dll.tobii_resume_device.restype = ctypes.c_int

api = ctypes.c_void_p()
dll.tobii_api_create(ctypes.byref(api), None, None)
device = ctypes.c_void_p()
url = b"tobii-prp://IS510-100211404854"
res = dll.tobii_device_create(api, url, 1, ctypes.byref(device))
print("device_create:", res)

res_resume = dll.tobii_resume_device(device)
print("resume_device:", res_resume)
