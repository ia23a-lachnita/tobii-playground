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

GUIDE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiUserPositionGuide), ctypes.c_void_p)

def on_guide(p_data, ud):
    d = p_data.contents
    print(f"  [USER_POS_GUIDE] L_val={d.left_eye_validity} L=({d.left_eye_x:.2f},{d.left_eye_y:.2f},{d.left_eye_z:.2f}) R_val={d.right_eye_validity} R=({d.right_eye_x:.2f},{d.right_eye_y:.2f},{d.right_eye_z:.2f})")

cb = GUIDE_CB(on_guide)

api = ctypes.c_void_p()
r_api = dll.tobii_api_create(ctypes.byref(api), None, None)
dev = ctypes.c_void_p()
r_dev = dll.tobii_device_create(api, b"tobii-prp://IS510-100211404854", 1, ctypes.byref(dev))
print(f"api_create: {r_api}, dev_create: {r_dev}")

dll.tobii_user_position_guide_subscribe.argtypes = [ctypes.c_void_p, GUIDE_CB, ctypes.c_void_p]
dll.tobii_user_position_guide_subscribe.restype = ctypes.c_int

r_sub = dll.tobii_user_position_guide_subscribe(dev, cb, None)
print(f"tobii_user_position_guide_subscribe result: {r_sub}")

dll.tobii_wait_for_callbacks.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
dll.tobii_wait_for_callbacks.restype = ctypes.c_int

dll.tobii_device_process_callbacks.argtypes = [ctypes.c_void_p]
dll.tobii_device_process_callbacks.restype = ctypes.c_int

if r_sub == 0:
    print("Listening for 5 seconds for User Position Guide packets...")
    t0 = time.time()
    count = 0
    while time.time() - t0 < 5.0:
        dev_ptr = ctypes.c_void_p(dev.value)
        dll.tobii_wait_for_callbacks(1, ctypes.byref(dev_ptr))
        dll.tobii_device_process_callbacks(dev)
    print("Finished listening.")
