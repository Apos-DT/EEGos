# -*- coding: utf-8 -*-
import time
import urllib.request

URL = "https://ojs.aaai.org/index.php/AAAI/article/download/27819/27668"
HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
req = urllib.request.Request(URL, headers=HEAD)
t0 = time.time()
with urllib.request.urlopen(req, timeout=30) as r:
    print("opened", r.status, r.headers.get("content-type"), r.headers.get("content-length"), flush=True)
    chunks = []
    total = 0
    while True:
        c = r.read(65536)
        if not c:
            break
        chunks.append(c)
        total += len(c)
        if total % (512 * 1024) < 65536:
            print("...", total, f"{time.time()-t0:.1f}s", flush=True)
        if time.time() - t0 > 60:
            print("TIMEOUT at", total, flush=True)
            break
    data = b"".join(chunks)
print("done", len(data), data[:5], f"{time.time()-t0:.1f}s", flush=True)
if data.startswith(b"%PDF"):
    open(r"C:\Users\24114\Desktop\EEG Emotion Recognition\文献\17_test.pdf", "wb").write(data)
