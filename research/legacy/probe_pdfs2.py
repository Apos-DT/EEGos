# -*- coding: utf-8 -*-
import re
import urllib.request

HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def probe(u, timeout=45):
    try:
        req = urllib.request.Request(u, headers=HEAD)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            print("OK", r.status, r.headers.get("content-type"), len(body), body[:5], u)
    except Exception as e:
        print("ERR", e, u)


for u in [
    "https://arxiv.org/pdf/2512.13458",
    "https://arxiv.org/pdf/2501.16230",
    "https://arxiv.org/pdf/2109.09559",
    "https://arxiv.org/pdf/2205.01030",
    "https://research-portal.uws.ac.uk/files/53642872/2017_03_19_Katsigiannis_et_al_DREAMER_accepted.pdf",
    "https://access.archive-ouverte.unige.ch/access/metadata/1d5ce2a8-00d8-4793-8943-cf9e8aa56693/download",
]:
    probe(u)

# D9 landing page: find download links
u = "https://archive-ouverte.unige.ch/unige:47406"
req = urllib.request.Request(u, headers=HEAD)
txt = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
links = sorted(set(re.findall(r'https?://[^"\']+(?:download|\.pdf)[^"\']*', txt)))
print("\nD9 links:")
for l in links[:20]:
    print(" ", l)
