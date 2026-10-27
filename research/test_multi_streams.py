import ctypes
import os
import sys
import time

DLL_PATH = os.path.abspath("x64_patched_tobii_stream_engine.dll")
dll = ctypes.CDLL(DLL_PATH)

class TobiiEyePositionNormalized(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("validity_left", ctypes.c_uint),
        ("position_left_x", ctypes.c_float),
        ("position_left_y", ctypes.c_float),
        ("position_left_z", ctypes.c_float),
        ("validity_right", ctypes.c_uint),
        ("position_right_x", ctypes.c_float),
        ("position_right_y", ctypes.c_float),
        ("position_right_z", ctypes.c_float),
    ]

class TobiiHeadPose(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("position_validity", ctypes.c_uint),
        ("position_x", ctypes.c_float),
        ("position_y", ctypes.c_float),
        ("position_z", ctypes.c_float),
        ("rotation_validity_x", ctypes.c_uint),
        ("rotation_validity_y", ctypes.c_uint),
        ("rotation_validity_z", ctypes.c_uint),
        ("rotation_x", ctypes.c_float),
        ("rotation_y", ctypes.c_float),
        ("rotation_z", ctypes.c_float),
    ]

class TobiiGazePoint(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("validity", ctypes.c_uint),
        ("position_x", ctypes.c_float),
        ("position_y", ctypes.c_float),
    ]

EYE_POS_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiEyePositionNormalized), ctypes.c_void_p)
HEAD_POSE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiHeadPose), ctypes.c_void_p)
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

def on_eye_pos(p_data, ud):
    d = p_data.contents
    print(f"  [EYE_POS] L_valid={d.validity_left} L=({d.position_left_x:.2f},{d.position_left_y:.2f},{d.position_left_z:.2f}) R_valid={d.validity_right} R=({d.position_right_x:.2f},{d.position_right_y:.2f},{d.position_right_z:.2f})")

def on_head_pose(p_data, ud):
    d = p_data.contents
    print(f"  [HEAD_POSE] valid={d.position_validity} pos=({d.position_x:.2f},{d.position_y:.2f},{d.position_z:.2f})")

def on_gaze(p_data, ud):
    d = p_data.contents
    print(f"  [GAZE] valid={d.validity} pos=({d.position_x:.4f},{d.position_y:.4f})")

cb1 = EYE_POS_CB(on_eye_pos)
cb2 = HEAD_POSE_CB(on_head_pose)
cb3 = GAZE_CB(on_gaze)

dll.tobii_eye_position_normalized_subscribe.argtypes = [ctypes.c_void_p, EYE_POS_CB, ctypes.c_void_p]
dll.tobii_eye_position_normalized_subscribe.restype = ctypes.c_int
r1 = dll.tobii_eye_position_normalized_subscribe(device, cb1, None)
print("eye_pos_sub:", r1)

dll.tobii_head_pose_subscribe.argtypes = [ctypes.c_void_p, HEAD_POSE_CB, ctypes.c_void_p]
dll.tobii_head_pose_subscribe.restype = ctypes.c_int
r2 = dll.tobii_head_pose_subscribe(device, cb2, None)
print("head_pose_sub:", r2)

dll.tobii_gaze_point_subscribe.argtypes = [ctypes.c_void_p, GAZE_CB, ctypes.c_void_p]
dll.tobii_gaze_point_subscribe.restype = ctypes.c_int
r3 = dll.tobii_gaze_point_subscribe(device, cb3, None)
print("gaze_sub:", r3)

print("Listening for 3 seconds...")
t0 = time.time()
while time.time() - t0 < 3.0:
    dev_ptr = ctypes.c_void_p(device.value)
    dll.tobii_wait_for_callbacks(1, ctypes.byref(dev_ptr))
    dll.tobii_device_process_callbacks(device)
print("Done")
