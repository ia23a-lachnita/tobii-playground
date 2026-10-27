import os, glob

p = r'C:\Program Files\Tobii\Tobii EyeX'
for fn in glob.glob(p + r'\*.dll') + glob.glob(p + r'\*.exe'):
    try:
        data = open(fn, 'rb').read()
        matches = [m.decode('ascii') for m in [b'MouseWarp', b'WarpOnKey', b'MouseControl', b'EyeControl', b'WindowsEyeControl', b'GazePointData', b'GazeSelection', b'Enterprise', b'License'] if m in data]
        if matches:
            print(f"{os.path.basename(fn)}: {matches}")
    except Exception as e:
        pass
