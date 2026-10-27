import pefile

pe = pefile.PE(r"C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.EyeTracking.dll")
print("EyeTracking.dll loaded")
data = open(r"C:\Program Files\Tobii\Tobii EyeX\Tobii.EyeX.EyeTracking.dll", "rb").read()
import re
matches = sorted(set(re.findall(rb'[A-Za-z0-9_]*Calibration[A-Za-z0-9_]*', data)))
for m in matches:
    print(m.decode(errors='ignore'))
