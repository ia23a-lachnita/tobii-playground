import ctypes
import os
import time

dll_path = os.path.abspath('x64_patched_tobii_stream_engine.dll')
dll = ctypes.CDLL(dll_path)

class TobiiUserPositionGuide(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("left_eye_validity", ctypes.c_uint),
        ("left_eye_x", ctypes.c_float),
        ("left_eye_y", ctypes.c_float),
        ("left_eye_z", ctypes.c_float),
        ("right_eye_validity", ctypes.c_uint),
        ("right_eye_x", ctypes.c_float),
        ("right_eye_y", ctypes.c_float),
        ("right_eye_z", ctypes.c_float),
    ]

cnt = 0
def on_guide(p_data, ud):
    global cnt
    cnt += 1
    d = p_data.contents
    print(f"GUIDE #{cnt}: L_val={d.left_eye_validity} R_val={d.right_eye_validity}")

cb = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiUserPositionGuide), ctypes.c_void_p)(on_guide)

api = ctypes.c_void_p()
dll.tobii_api_create(ctypes.byref(api), None, None)
dev = ctypes.c_void_p()
dll.tobii_device_create(api, b"tobii-prp://IS510-100211404854", 1, ctypes.byref(dev))

dll.tobii_user_position_guide_subscribe.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
dll.tobii_user_position_guide_subscribe.restype = ctypes.c_int
r = dll.tobii_user_position_guide_subscribe(dev, cb, None)
print("subscribe result:", r)

dll.tobii_wait_for_callbacks.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
dll.tobii_wait_for_callbacks.restype = ctypes.c_int
dll.tobii_device_process_callbacks.argtypes = [ctypes.c_void_p]
dll.tobii_device_process_callbacks.restype = ctypes.c_int

dev_ptr = ctypes.c_void_p(dev.value)
for i in range(10):
    w = dll.tobii_wait_for_callbacks(1, ctypes.byref(dev_ptr))
    p = dll.tobii_device_process_callbacks(dev)
    print(f"wait: {w}, process: {p}, total received: {cnt}")
