# -*- coding: utf-8 -*-
import re
import urllib.request

HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 06 SSAS: check size and range support
u = "https://arxiv.org/pdf/2512.13458"
try:
    req = urllib.request.Request(u, headers={**HEAD, "Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print("SSAS range", r.status, r.headers.get("content-range"), r.headers.get("content-length"))
except Exception as e:
    print("SSAS range ERR", e)

# D7 landing page links
u = "https://research-portal.uws.ac.uk/en/publications/8d7c9368-487e-400a-b6db-78fb05677551"
try:
    txt = urllib.request.urlopen(urllib.request.Request(u, headers=HEAD), timeout=30).read().decode("utf-8", "ignore")
    links = sorted(set(re.findall(r'href="([^"]*(?:\.pdf|/files/)[^"]*)"', txt)))
    print("D7 links:")
    for l in links[:15]:
        print("  ", l)
except Exception as e:
    print("D7 page ERR", e)
