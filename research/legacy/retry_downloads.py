# -*- coding: utf-8 -*-
import os
import time
import urllib.request

OUT = r"C:\Users\24114\Desktop\EEG Emotion Recognition\文献"
HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# ---- resume SSAS ----
part = os.path.join(OUT, "06_SSAS_Source_Selection_Adversarial_Strategy_2026.pdf.part")
final = part[:-5]
u = "https://arxiv.org/pdf/2512.13458"
have = os.path.getsize(part)
print("resume from", have, flush=True)
t0 = time.time()
try:
    req = urllib.request.Request(u, headers={**HEAD, "Range": f"bytes={have}-"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print("status", r.status, r.headers.get("content-range"), flush=True)
        with open(part, "ab") as f:
            while True:
                c = r.read(65536)
                if not c:
                    break
                f.write(c)
                have += len(c)
                if time.time() - t0 > 180:
                    print("timeout at", have, flush=True)
                    break
    print("size now", os.path.getsize(part), flush=True)
    with open(part, "rb") as f:
        magic = f.read(5)
        f.seek(-1024, 2)
        tail = f.read()
    print("magic", magic, "eof", b"%%EOF" in tail, flush=True)
    if magic == b"%PDF-" and b"%%EOF" in tail:
        os.replace(part, final)
        print("SSAS OK", flush=True)
except Exception as e:
    print("SSAS ERR", type(e).__name__, e, flush=True)

# ---- DREAMER with referer ----
u = "https://research-portal.uws.ac.uk/files/53642872/2017_03_19_Katsigiannis_et_al_DREAMER_accepted.pdf"
try:
    req = urllib.request.Request(u, headers={
        **HEAD,
        "Referer": "https://research-portal.uws.ac.uk/en/publications/8d7c9368-487e-400a-b6db-78fb05677551",
        "Accept": "application/pdf,*/*",
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        data = r.read()
    print("DREAMER", r.status, r.headers.get("content-type"), len(data), data[:5], flush=True)
    if data.startswith(b"%PDF"):
        open(os.path.join(OUT, "D7_DREAMER_EEG_ECG_Database_2018.pdf"), "wb").write(data)
        print("DREAMER OK", flush=True)
except Exception as e:
    print("DREAMER ERR", type(e).__name__, e, flush=True)
