import re

d = open(r'C:\Program Files\Tobii\Tobii EyeX\Tobii.Configuration.exe', 'rb').read()
strings = re.findall(rb'[a-zA-Z0-9_\-\.\/]{3,}', d)
for s in strings:
    st = s.decode(errors='replace')
    if st.startswith('-') or st.startswith('/'):
        if len(st) > 2 and not st.startswith('//'):
            print(st)
