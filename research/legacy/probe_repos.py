# -*- coding: utf-8 -*-
import re
import urllib.request

HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def get(u, timeout=30):
    req = urllib.request.Request(u, headers=HEAD)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers.get("content-type"), r.read()


for u in [
    "https://archive-ouverte.unige.ch/unige:47405",
    "https://archive-ouverte.unige.ch/unige:47406",
    "https://research-portal.uws.ac.uk/en/publications/8d7c9368-487e-400a-b6db-78fb05677551",
]:
    try:
        st, ct, body = get(u)
        txt = body.decode("utf-8", "ignore")
        print("\nPAGE", u, st, len(body), ct)
        pdfs = re.findall(r'href="([^"]+\.pdf[^"]*)"', txt, re.I)
        print("PDF links:", pdfs[:8])
        m = re.search(r'citation_pdf_url"\s+content="([^"]+)"', txt, re.I)
        print("citation_pdf_url:", m.group(1) if m else None)
    except Exception as e:
        print("ERR", u, e)

for u in [
    "https://ieeexplore.ieee.org/ielx7/6287639/8600701/08606087.pdf",
    "https://www.nature.com/articles/s41597-023-02650-w.pdf",
    "https://ojs.aaai.org/index.php/AAAI/article/download/27819/27668",
    "https://arxiv.org/pdf/2203.11279",
]:
    try:
        st, ct, body = get(u, timeout=45)
        print("\nPDF", u, st, ct, len(body), body[:5])
    except Exception as e:
        print("PDF ERR", u, e)
