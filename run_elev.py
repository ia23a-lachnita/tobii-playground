import ctypes

user32 = ctypes.windll.user32
shell_wnd = user32.GetShellWindow()
desktop_wnd = user32.GetDesktopWindow()
fg_wnd = user32.GetForegroundWindow()
print(f"Shell window: 0x{shell_wnd:x}, Desktop window: 0x{desktop_wnd:x}, Foreground window: 0x{fg_wnd:x}")

# Try ShellExecuteW with desktop window
ret = ctypes.windll.shell32.ShellExecuteW(
    desktop_wnd,
    'runas',
    'cmd.exe',
    r'/c "C:\Users\xursc\projects\tobii_playground\deploy_service.cmd"',
    r'C:\Users\xursc\projects\tobii_playground',
    0
)
print("ShellExecuteW with desktop_wnd returned:", ret)
if ret <= 32:
    print("GetLastError:", ctypes.GetLastError())
