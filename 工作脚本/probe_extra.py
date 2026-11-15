# -*- coding: utf-8 -*-
import re
import urllib.request

HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

for u in [
    "https://durham-repository.worktribe.com/output/1261675",
    "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5174448",
]:
    try:
        txt = urllib.request.urlopen(urllib.request.Request(u, headers=HEAD), timeout=30).read().decode("utf-8", "ignore")
        print("\nPAGE", u, len(txt))
        links = sorted(set(re.findall(r'(?:href|content)="([^"]*(?:\.pdf|Delivery\.cfm)[^"]*)"', txt, re.I)))
        for l in links[:15]:
            print("  ", l)
    except Exception as e:
        print("ERR", u, type(e).__name__, e)
