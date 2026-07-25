"""Test WebSocket connection to TobiiGhost"""
import websocket
import json
import time

ws = websocket.create_connection("ws://127.0.0.1:7890", timeout=5)
print("Connected to WebSocket!")

messages = [
    "{}",
    '{"type":"get_device_info"}',
    '{"action":"get_device_info"}',
    '{"method":"get_device_info"}',
    '{"command":"get_device_info"}',
    '{"type":"ping"}',
    '{"action":"ping"}',
    '{"type":"subscribe","stream":"gaze"}',
    '{"type":"subscribe","channel":"gaze"}',
    '{"type":"gaze_subscribe"}',
    '{"type":"start"}',
    '{"type":"get_status"}',
    '{"type":"info"}',
]

for msg in messages:
    try:
        ws.send(msg)
        result = ws.recv()
        print(f"Sent: {msg}")
        print(f"Received: {result[:500]}")
        print()
    except Exception as e:
        print(f"Sent: {msg}, Error: {e}")
        break

ws.close()
