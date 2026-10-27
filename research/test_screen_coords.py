import ctypes
import os
import sys
import time

DLL_PATH = os.path.abspath("x64_patched_tobii_stream_engine.dll")
dll = ctypes.CDLL(DLL_PATH)

class TobiiGazePoint(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("validity", ctypes.c_uint),
        ("position_x", ctypes.c_float),
        ("position_y", ctypes.c_float),
    ]

GAZE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiGazePoint), ctypes.c_void_p)

dll.tobii_api_create.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_void_p]
dll.tobii_api_create.restype = ctypes.c_int
dll.tobii_device_create.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
dll.tobii_device_create.restype = ctypes.c_int
dll.tobii_wait_for_callbacks.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
dll.tobii_wait_for_callbacks.restype = ctypes.c_int
dll.tobii_device_process_callbacks.argtypes = [ctypes.c_void_p]
dll.tobii_device_process_callbacks.restype = ctypes.c_int

api = ctypes.c_void_p()
dll.tobii_api_create(ctypes.byref(api), None, None)
device = ctypes.c_void_p()
url = b"tobii-prp://IS510-100211404854"
dll.tobii_device_create(api, url, 1, ctypes.byref(device))

points = []
def on_gaze(p_data, ud):
    d = p_data.contents
    if d.validity == 1:
        px = int(d.position_x * 1920)
        py = int(d.position_y * 1080)
        points.append((d.position_x, d.position_y, px, py))

cb = GAZE_CB(on_gaze)
dll.tobii_gaze_point_subscribe.argtypes = [ctypes.c_void_p, GAZE_CB, ctypes.c_void_p]
dll.tobii_gaze_point_subscribe.restype = ctypes.c_int
res = dll.tobii_gaze_point_subscribe(device, cb, None)

print("Subscribed:", res)
t0 = time.time()
while time.time() - t0 < 2.0:
    dev_ptr = ctypes.c_void_p(device.value)
    dll.tobii_wait_for_callbacks(1, ctypes.byref(dev_ptr))
    dll.tobii_device_process_callbacks(device)

print(f"Valid gaze points received: {len(points)}")
if points:
    print(f"Sample: norm=({points[-1][0]:.3f}, {points[-1][1]:.3f}) -> screen=({points[-1][2]}, {points[-1][3]})")
