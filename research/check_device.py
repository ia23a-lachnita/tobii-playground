import ctypes
import os

dll_path = os.path.abspath('x64_patched_tobii_stream_engine.dll')
dll = ctypes.CDLL(dll_path)
api = ctypes.c_void_p()
r = dll.tobii_api_create(ctypes.byref(api), None, None)
dev = ctypes.c_void_p()
r2 = dll.tobii_device_create(api, b'tobii-prp://IS510-100211404854', 1, ctypes.byref(dev))
print('api_create:', r, 'dev_create:', r2, 'dev:', dev.value)
