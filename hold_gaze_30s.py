import ctypes
import os
import time

dll_path = os.path.abspath('x64_patched_tobii_stream_engine.dll')
dll = ctypes.CDLL(dll_path)

class TobiiGazePoint(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("validity", ctypes.c_uint),
        ("position_x", ctypes.c_float),
        ("position_y", ctypes.c_float),
    ]

GAZE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiGazePoint), ctypes.c_void_p)
def on_gaze(p, u): pass
cb = GAZE_CB(on_gaze)

api = ctypes.c_void_p()
dll.tobii_api_create(ctypes.byref(api), None, None)
dev = ctypes.c_void_p()
dll.tobii_device_create(api, b"tobii-prp://IS510-100211404854", 1, ctypes.byref(dev))
dll.tobii_gaze_point_subscribe.argtypes = [ctypes.c_void_p, GAZE_CB, ctypes.c_void_p]
dll.tobii_gaze_point_subscribe.restype = ctypes.c_int
r = dll.tobii_gaze_point_subscribe(dev, cb, None)
print("Background gaze stream active:", r)

dll.tobii_wait_for_callbacks.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
dll.tobii_wait_for_callbacks.restype = ctypes.c_int
dll.tobii_device_process_callbacks.argtypes = [ctypes.c_void_p]
dll.tobii_device_process_callbacks.restype = ctypes.c_int

dev_ptr = ctypes.c_void_p(dev.value)
t0 = time.time()
while time.time() - t0 < 30.0:
    dll.tobii_wait_for_callbacks(1, ctypes.byref(dev_ptr))
    dll.tobii_device_process_callbacks(dev)
