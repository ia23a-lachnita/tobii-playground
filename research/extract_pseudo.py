"""Extract pseudo_code (and nearby gate-relevant lines) from the rea
analyze_function spillover JSON for the VID:PID gate function."""
import re, json, sys

f = r"C:\Users\xursc\AppData\Local\hermes\cache\spillover\chatcmpl-tool-b8e36de21ad79ff7.txt"
s = open(f, encoding="utf-8", errors="replace").read()

def extract_json_string(s, start):
    """Decode a JSON string starting right after the opening quote."""
    out = []
    i = start
    while i < len(s):
        c = s[i]
        if c == "\\":
            nxt = s[i + 1] if i + 1 < len(s) else ""
            mp = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/"}
            if nxt in mp:
                out.append(mp[nxt]); i += 2; continue
            if nxt == "u":
                out.append(chr(int(s[i + 2:i + 6], 16))); i += 6; continue
            out.append(nxt); i += 2; continue
        if c == '"':
            break
        out.append(c); i += 1
    return "".join(out), i

targets = sys.argv[1:] or ["pseudo_code"]
for field in targets:
    for m in re.finditer(r'"' + field + r'"\s*:\s*"', s):
        val, end = extract_json_string(s, m.end())
        print(f"=== {field} ({len(val)} chars) ===")
        print(val)
        print()
