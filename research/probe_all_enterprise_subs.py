import ctypes
import os
import sys

DLL_PATH = os.path.abspath("x64_patched_tobii_stream_engine.dll")
dll = ctypes.CDLL(DLL_PATH)

dll.tobii_api_create.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_void_p]
dll.tobii_api_create.restype = ctypes.c_int
dll.tobii_device_create.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
dll.tobii_device_create.restype = ctypes.c_int

api = ctypes.c_void_p()
dll.tobii_api_create(ctypes.byref(api), None, None)
device = ctypes.c_void_p()
url = b"tobii-prp://IS510-100211404854"
dll.tobii_device_create(api, url, 1, ctypes.byref(device))

# List of subscription functions to probe
DUMMY_CB = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)
cb = DUMMY_CB(lambda p, u: None)

sub_funcs = [
    "tobii_gaze_point_subscribe",
    "tobii_head_pose_subscribe",
    "tobii_user_position_guide_subscribe",
    "tobii_eye_position_normalized_subscribe",
    "tobii_gaze_origin_subscribe",
    "tobii_gaze_data_subscribe",
    "tobii_user_presence_subscribe",
    "tobii_absolute_eye_openness_subscribe",
    "tobii_wearable_entrance_pupil_position_subscribe",
    "tobii_wearable_consumer_data_subscribe",
    "tobii_wearable_advanced_data_subscribe",
    "tobii_facial_landmarks_3d_subscribe",
    "tobii_foveated_rendering_gaze_point_subscribe",
]

for name in sub_funcs:
    func = getattr(dll, name, None)
    if func:
        func.argtypes = [ctypes.c_void_p, DUMMY_CB, ctypes.c_void_p]
        func.restype = ctypes.c_int
        res = func(device, cb, None)
        print(f"{name:50s} -> {res}")
    else:
        print(f"{name:50s} -> NOT FOUND")
