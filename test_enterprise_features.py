#!/usr/bin/env python3
"""
Tobii Eye Tracker 5L - Enterprise SDK Feature Suite Verification
===============================================================
Demonstrates and validates:
  1. Gaze Point (Calibrated 2D screen coordinates)
  2. Head Pose (6DOF: 3D position + pitch/yaw/roll rotations)
  3. User Position Guide (Real-time 3D eye tracking box)
  4. User Presence (Detection & approach telemetry)
  5. Multi-stream concurrent acquisition
"""

import ctypes
from ctypes import byref
import os
import sys
import time

DLL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "x64_patched_tobii_stream_engine.dll"))
dll = ctypes.CDLL(DLL_PATH)

# C Data Structures
class TobiiGazePoint(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("validity", ctypes.c_uint),
        ("position_x", ctypes.c_float),
        ("position_y", ctypes.c_float),
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

class TobiiVector3(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float), ("z", ctypes.c_float)]

class TobiiUserPositionGuide(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("left_validity", ctypes.c_uint),
        ("left_xyz", TobiiVector3),
        ("right_validity", ctypes.c_uint),
        ("right_xyz", TobiiVector3),
    ]

class TobiiPresence(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("status", ctypes.c_uint),
    ]

# Callbacks
GAZE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiGazePoint), ctypes.c_void_p)
HEAD_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiHeadPose), ctypes.c_void_p)
GUIDE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiUserPositionGuide), ctypes.c_void_p)
PRESENCE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiPresence), ctypes.c_void_p)

# Global stats
stats = {
    "gaze_frames": 0,
    "head_frames": 0,
    "guide_frames": 0,
    "presence_frames": 0,
    "latest_gaze": None,
    "latest_head": None,
    "latest_guide": None,
}

def on_gaze(p, ud):
    d = p.contents
    stats["gaze_frames"] += 1
    if d.validity == 1:
        stats["latest_gaze"] = (d.position_x, d.position_y)

def on_head(p, ud):
    d = p.contents
    stats["head_frames"] += 1
    if d.position_validity == 1:
        stats["latest_head"] = (d.position_x, d.position_y, d.position_z, d.rotation_x, d.rotation_y, d.rotation_z)

def on_guide(p, ud):
    d = p.contents
    stats["guide_frames"] += 1
    if d.left_validity == 1 or d.right_validity == 1:
        stats["latest_guide"] = (d.left_validity, d.left_xyz.x, d.left_xyz.y, d.left_xyz.z,
                                 d.right_validity, d.right_xyz.x, d.right_xyz.y, d.right_xyz.z)

def on_presence(p, ud):
    stats["presence_frames"] += 1

cb_gaze = GAZE_CB(on_gaze)
cb_head = HEAD_CB(on_head)
cb_guide = GUIDE_CB(on_guide)
cb_pres = PRESENCE_CB(on_presence)

def main():
    print("=" * 70)
    print("     Tobii Eye Tracker 5L - Enterprise SDK Capability Test Suite     ")
    print("=" * 70)

    dll.tobii_api_create.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_void_p]
    dll.tobii_api_create.restype = ctypes.c_int
    dll.tobii_device_create.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
    dll.tobii_device_create.restype = ctypes.c_int
    dll.tobii_wait_for_callbacks.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
    dll.tobii_wait_for_callbacks.restype = ctypes.c_int
    dll.tobii_device_process_callbacks.argtypes = [ctypes.c_void_p]
    dll.tobii_device_process_callbacks.restype = ctypes.c_int

    api = ctypes.c_void_p()
    dll.tobii_api_create(byref(api), None, None)
    device = ctypes.c_void_p()
    url = b"tobii-prp://IS510-100211404854"
    res = dll.tobii_device_create(api, url, 1, byref(device))
    if res != 0:
        print(f"Error: failed to connect to tracker (code {res})")
        return

    # Subscribe to streams
    dll.tobii_gaze_point_subscribe.argtypes = [ctypes.c_void_p, GAZE_CB, ctypes.c_void_p]
    dll.tobii_gaze_point_subscribe.restype = ctypes.c_int
    r1 = dll.tobii_gaze_point_subscribe(device, cb_gaze, None)

    dll.tobii_head_pose_subscribe.argtypes = [ctypes.c_void_p, HEAD_CB, ctypes.c_void_p]
    dll.tobii_head_pose_subscribe.restype = ctypes.c_int
    r2 = dll.tobii_head_pose_subscribe(device, cb_head, None)

    dll.tobii_user_position_guide_subscribe.argtypes = [ctypes.c_void_p, GUIDE_CB, ctypes.c_void_p]
    dll.tobii_user_position_guide_subscribe.restype = ctypes.c_int
    r3 = dll.tobii_user_position_guide_subscribe(device, cb_guide, None)

    dll.tobii_user_presence_subscribe.argtypes = [ctypes.c_void_p, PRESENCE_CB, ctypes.c_void_p]
    dll.tobii_user_presence_subscribe.restype = ctypes.c_int
    r4 = dll.tobii_user_presence_subscribe(device, cb_pres, None)

    print(f" [1] Gaze Point Stream:          Subscription Status = {r1} (0=OK)")
    print(f" [2] Head Pose (6DOF) Stream:     Subscription Status = {r2} (0=OK)")
    print(f" [3] User Position Guide Stream:  Subscription Status = {r3} (0=OK)")
    print(f" [4] User Presence Stream:        Subscription Status = {r4} (0=OK)")
    print("-" * 70)
    print(" Streaming real-time multi-stream telemetry for 4 seconds...")

    t0 = time.time()
    while time.time() - t0 < 4.0:
        dev_ptr = ctypes.c_void_p(device.value)
        dll.tobii_wait_for_callbacks(1, byref(dev_ptr))
        dll.tobii_device_process_callbacks(device)

    print("\n" + "=" * 70)
    print(" Telemetry Results Summary:")
    print("=" * 70)
    print(f"  * Gaze Point frames received:         {stats['gaze_frames']}")
    if stats['latest_gaze']:
        print(f"    -> Latest Gaze (norm):              x={stats['latest_gaze'][0]:.3f}, y={stats['latest_gaze'][1]:.3f}")
    print(f"  * Head Pose (6DOF) frames received:   {stats['head_frames']}")
    if stats['latest_head']:
        h = stats['latest_head']
        print(f"    -> Head Position (mm):              x={h[0]:.1f}, y={h[1]:.1f}, z={h[2]:.1f}")
        print(f"    -> Head Rotation (deg):             pitch={h[3]:.1f}, yaw={h[4]:.1f}, roll={h[5]:.1f}")
    print(f"  * User Position Guide frames:         {stats['guide_frames']}")
    if stats['latest_guide']:
        g = stats['latest_guide']
        print(f"    -> 3D Eye Position Box:             L_valid={g[0]}, R_valid={g[4]}")
    print(f"  * User Presence frames received:      {stats['presence_frames']}")
    print("=" * 70)

if __name__ == "__main__":
    main()
