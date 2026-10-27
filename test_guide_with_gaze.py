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

class TobiiGazePoint(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("validity", ctypes.c_uint),
        ("position_x", ctypes.c_float),
        ("position_y", ctypes.c_float),
    ]

GUIDE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiUserPositionGuide), ctypes.c_void_p)
GAZE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiGazePoint), ctypes.c_void_p)

guide_count = 0
gaze_count = 0

def on_guide(p_data, ud):
    global guide_count
    guide_count += 1
    d = p_data.contents
    if guide_count <= 5 or guide_count % 30 == 0:
        print(f"  [USER_POS_GUIDE #{guide_count}] L_val={d.left_eye_validity} L=({d.left_eye_x:.2f},{d.left_eye_y:.2f},{d.left_eye_z:.2f}) R_val={d.right_eye_validity} R=({d.right_eye_x:.2f},{d.right_eye_y:.2f},{d.right_eye_z:.2f})")

def on_gaze(p_data, ud):
    global gaze_count
    gaze_count += 1
    d = p_data.contents
    if gaze_count <= 5 or gaze_count % 30 == 0:
        print(f"  [GAZE #{gaze_count}] val={d.validity} pos=({d.position_x:.4f},{d.position_y:.4f})")

cb_guide = GUIDE_CB(on_guide)
cb_gaze = GAZE_CB(on_gaze)

api = ctypes.c_void_p()
r_api = dll.tobii_api_create(ctypes.byref(api), None, None)
dev = ctypes.c_void_p()
r_dev = dll.tobii_device_create(api, b"tobii-prp://IS510-100211404854", 1, ctypes.byref(dev))

dll.tobii_gaze_point_subscribe.argtypes = [ctypes.c_void_p, GAZE_CB, ctypes.c_void_p]
dll.tobii_gaze_point_subscribe.restype = ctypes.c_int
r_gaze = dll.tobii_gaze_point_subscribe(dev, cb_gaze, None)

dll.tobii_user_position_guide_subscribe.argtypes = [ctypes.c_void_p, GUIDE_CB, ctypes.c_void_p]
dll.tobii_user_position_guide_subscribe.restype = ctypes.c_int
r_guide = dll.tobii_user_position_guide_subscribe(dev, cb_guide, None)

print(f"gaze_sub: {r_gaze}, guide_sub: {r_guide}")

dll.tobii_wait_for_callbacks.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
dll.tobii_wait_for_callbacks.restype = ctypes.c_int
dll.tobii_device_process_callbacks.argtypes = [ctypes.c_void_p]
dll.tobii_device_process_callbacks.restype = ctypes.c_int

print("Streaming for 4 seconds...")
t0 = time.time()
while time.time() - t0 < 4.0:
    dev_ptr = ctypes.c_void_p(dev.value)
    dll.tobii_wait_for_callbacks(1, ctypes.byref(dev_ptr))
    dll.tobii_device_process_callbacks(dev)

print(f"Finished: total gaze frames={gaze_count}, total guide frames={guide_count}")
