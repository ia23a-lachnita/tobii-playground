import ctypes
import os
import time

DLL_PATH = os.path.abspath("x64_patched_tobii_stream_engine.dll")
dll = ctypes.CDLL(DLL_PATH)

class TobiiVector3(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("z", ctypes.c_float),
    ]

class TobiiGazeOrigin(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("left_validity", ctypes.c_uint),
        ("left_xyz", TobiiVector3),
        ("right_validity", ctypes.c_uint),
        ("right_xyz", TobiiVector3),
    ]

GAZE_ORIGIN_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiGazeOrigin), ctypes.c_void_p)

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

frames = []
def on_gaze_origin(p_data, ud):
    d = p_data.contents
    frames.append((d.left_validity, d.left_xyz.x, d.left_xyz.y, d.left_xyz.z,
                   d.right_validity, d.right_xyz.x, d.right_xyz.y, d.right_xyz.z))
    if len(frames) <= 10:
        print(f"GazeOrigin: L_val={d.left_validity} L=({d.left_xyz.x:.1f}, {d.left_xyz.y:.1f}, {d.left_xyz.z:.1f} mm) R_val={d.right_validity} R=({d.right_xyz.x:.1f}, {d.right_xyz.y:.1f}, {d.right_xyz.z:.1f} mm)")

cb = GAZE_ORIGIN_CB(on_gaze_origin)
dll.tobii_gaze_origin_subscribe.argtypes = [ctypes.c_void_p, GAZE_ORIGIN_CB, ctypes.c_void_p]
dll.tobii_gaze_origin_subscribe.restype = ctypes.c_int

res = dll.tobii_gaze_origin_subscribe(device, cb, None)
print("gaze_origin_sub res:", res)

t0 = time.time()
while time.time() - t0 < 2.0:
    dev_ptr = ctypes.c_void_p(device.value)
    dll.tobii_wait_for_callbacks(1, ctypes.byref(dev_ptr))
    dll.tobii_device_process_callbacks(device)

print(f"Total gaze origin frames received: {len(frames)}")
