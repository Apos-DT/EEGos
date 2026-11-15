# -*- coding: utf-8 -*-
import json
import urllib.request
import urllib.parse
import time

ITEMS = [
    ("01", "10.1145/3524499"),
    ("02", "10.1145/3666002"),
    ("03", "10.1016/j.neucom.2025.130418"),
    ("04", "10.1109/JBHI.2022.3210158"),
    ("05", "10.1109/TIM.2025.3551924"),
    ("06", "10.1016/j.eswa.2025.130843"),
    ("07", "10.1109/TAFFC.2018.2885474"),
    ("08", "10.1109/TAFFC.2025.3588873"),
    ("09", "10.1109/TIM.2025.3553234"),
    ("10", "10.1016/j.neunet.2024.106742"),
    ("11", "10.1145/3746027.3754775"),
    ("12", "10.1109/TAFFC.2025.3608571"),
    ("13", "10.1109/TAFFC.2026.3671020"),
    ("14", "10.1109/TAFFC.2025.3580787"),
    ("15", "10.1109/TAFFC.2022.3164516"),
    ("16", "10.1109/TAFFC.2022.3170428"),
    ("17", "10.1609/aaai.v38i1.27819"),
    ("18", "10.1109/TAFFC.2025.3535542"),
    ("19", "10.1016/j.inffus.2026.104224"),
    ("20", "10.1109/TAFFC.2024.3485057"),
    ("D1", "10.1109/TAMD.2015.2431497"),
    ("D2", "10.1109/TCYB.2018.2797176"),
    ("D5", "10.1109/T-AFFC.2011.15"),
    ("D6", "10.1109/ACCESS.2019.2891579"),
    ("D7", "10.1109/JBHI.2017.2688239"),
    ("D8", "10.1038/s41597-023-02650-w"),
    ("D9", "10.1109/T-AFFC.2011.25"),
]

for key, doi in ITEMS:
    url = f"https://api.unpaywall.org/v2/{doi}?email=test@test.com"
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
            d = json.load(r)
        best = d.get("best_oa_location") or {}
        print(f"{key}\t{d.get('is_oa')}\t{(d.get('title') or '')[:70]}\tPDF={best.get('url_for_pdf')}\tURL={best.get('url')}")
        for loc in (d.get("oa_locations") or [])[:3]:
            print(f"    - {loc.get('host_type')} {loc.get('url_for_pdf') or loc.get('url')}")
    except Exception as e:
        print(f"{key}\tERR\t{e}")
    time.sleep(0.4)
